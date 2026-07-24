use serde::Serialize;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{IpAddr, Ipv4Addr, SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::Manager;
use uuid::Uuid;

struct GatewayProcess {
    child: Child,
    connection: GatewayConnection,
}

impl Drop for GatewayProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct GatewayConnection {
    base_url: String,
    token: String,
    workspace: String,
}

#[derive(Default)]
struct GatewayState(Mutex<Option<GatewayProcess>>);

fn console_root() -> Result<PathBuf, String> {
    let manifest = Path::new(env!("CARGO_MANIFEST_DIR"));
    manifest
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| "Could not locate the Rocketry Console directory.".to_string())
}

fn available_port() -> Result<u16, String> {
    let listener = std::net::TcpListener::bind(("127.0.0.1", 0))
        .map_err(|error| format!("Could not reserve a gateway port: {error}"))?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| format!("Could not read the gateway port: {error}"))
}

fn wait_for_gateway(child: &mut Child, port: u16) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(12);
    let address = SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), port);
    while Instant::now() < deadline {
        if let Some(status) = child
            .try_wait()
            .map_err(|error| format!("Could not inspect the gateway process: {error}"))?
        {
            return Err(format!("The gateway exited during startup with {status}."));
        }
        if let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(250)) {
            let _ = stream.set_read_timeout(Some(Duration::from_secs(1)));
            let request = b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
            if stream.write_all(request).is_ok() {
                let mut response = String::new();
                if stream.read_to_string(&mut response).is_ok()
                    && response.starts_with("HTTP/1.1 200")
                    && response.contains("\"ok\":true")
                {
                    return Ok(());
                }
            }
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    Err("The gateway did not accept HTTP requests within 12 seconds.".to_string())
}

#[tauri::command]
fn start_gateway(state: tauri::State<GatewayState>) -> Result<GatewayConnection, String> {
    let mut process = state
        .0
        .lock()
        .map_err(|_| "The gateway state lock is unavailable.".to_string())?;
    if let Some(existing) = process.as_mut() {
        if existing.child.try_wait().map_err(|error| error.to_string())?.is_none() {
            return Ok(existing.connection.clone());
        }
        *process = None;
    }

    let root = console_root()?;
    let workspace = root
        .parent()
        .ok_or_else(|| "Could not locate the repository workspace.".to_string())?
        .to_path_buf();
    let python = root.join(".venv/bin/python");
    if !python.is_file() {
        return Err(format!(
            "Python environment not found at {}. Run the console setup first.",
            python.display()
        ));
    }
    let port = available_port()?;
    let token = Uuid::new_v4().simple().to_string();
    let database = root.join(".rocketry/gateway.db");
    let mut child = Command::new(python)
        .args(["-m", "gateway.server"])
        .current_dir(&root)
        .env("ROCKETRY_GATEWAY_TOKEN", &token)
        .env("ROCKETRY_GATEWAY_PORT", port.to_string())
        .env("ROCKETRY_GATEWAY_DB", database)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("Could not start the local gateway: {error}"))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "The gateway did not expose its startup channel.".to_string())?;
    let (sender, receiver) = std::sync::mpsc::sync_channel(1);
    std::thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        let mut first_line = String::new();
        let first = reader.read_line(&mut first_line).map(|_| first_line);
        let _ = sender.send(first);
        for line in reader.lines() {
            if line.is_err() {
                break;
            }
        }
    });
    let startup = receiver
        .recv_timeout(Duration::from_secs(12))
        .map_err(|_| "The gateway did not become ready within 12 seconds.".to_string())?
        .map_err(|error| format!("Could not read gateway startup: {error}"))?;
    if !startup.contains("gateway_ready") {
        let _ = child.kill();
        return Err(format!("Unexpected gateway startup response: {startup}"));
    }
    if let Err(error) = wait_for_gateway(&mut child, port) {
        let _ = child.kill();
        let _ = child.wait();
        return Err(error);
    }
    let connection = GatewayConnection {
        base_url: format!("http://127.0.0.1:{port}"),
        token,
        workspace: workspace.to_string_lossy().into_owned(),
    };
    *process = Some(GatewayProcess {
        child,
        connection: connection.clone(),
    });
    Ok(connection)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(GatewayState::default())
        .setup(|app| {
            start_gateway(app.state::<GatewayState>())
                .map(|_| ())
                .map_err(std::io::Error::other)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![start_gateway])
        .run(tauri::generate_context!())
        .expect("error while running Rocketry Workstation");
}
