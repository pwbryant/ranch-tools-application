const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const spawn = require('cross-spawn');
const path = require('path');
const http = require('http');
const fs = require('fs');

// Detect if running in development or production
const isDev = !app.isPackaged;


// Create log file path
const logPath = isDev
    ? path.join(__dirname, 'debug.log')
    : path.join(process.resourcesPath, '..', 'debug.log'); // Goes to install directory


function writeLog(message) {
    const timestamp = new Date().toISOString();
    const logEntry = `${timestamp}: ${message}\n`;
    fs.appendFileSync(logPath, logEntry);
}

let mainWindow;
let djangoProcess;

// Set paths based on environment
const DJANGO_PATH = isDev 
    ? path.join(__dirname, '..', 'django_project')
    : path.join(process.resourcesPath, 'django_project');

const PYTHON_PATH = isDev 
    ? getPythonForDevelopment()
    : path.join(process.resourcesPath, 'python-embed', 'python.exe');

function getPythonForDevelopment() {
    // Check for virtual environment first (recommended for development)
    const venvPython = path.join(__dirname, '..', 'django_project', 'venv', 'Scripts', 'python.exe');
    if (fs.existsSync(venvPython)) {
        console.log('Using virtual environment Python:', venvPython);
        return venvPython;
    }
    
    // Fall back to system Python
    console.log('Virtual environment not found, using system Python');
    return 'python'; // This will use whatever 'python' command is in PATH
}

console.log('Environment:', isDev ? 'Development' : 'Production');
console.log('Django Path:', DJANGO_PATH);
console.log('Python Path:', PYTHON_PATH);


function updateLoadingStatus(message) {
    if (mainWindow) {
        mainWindow.webContents.executeJavaScript(`
            document.getElementById('status').textContent = '${message}';
        `);
    }
}

function waitForDjango(callback, maxAttempts = 100) {
    let attempts = 0;
    
    const checkDjango = () => {
        attempts++;
        updateLoadingStatus(`Connecting to application... (${attempts}/${maxAttempts})`);

        const req = http.get('http://localhost:8000/pregchecks', (res) => {
            writeLog('Django is ready!');
            console.log('Django is ready!');
            updateLoadingStatus('Application ready! Loading...');
            callback();
        });
        
        req.on('error', (err) => {
            if (attempts < maxAttempts) {
                console.log(`Waiting for Django... (attempt ${attempts})`);
                setTimeout(checkDjango, 1000);
            } else {
                console.error('Django failed to start within timeout period');
                updateLoadingStatus('Failed to start application. Please try restarting.');
            }
        });
    };
    
    checkDjango();
}

function startDjango() {
    updateLoadingStatus('Starting application server...');
    console.log('Starting Django server...');
    console.log('isDev:', isDev);
    console.log('Django Path exists:', require('fs').existsSync(DJANGO_PATH));
    console.log('Python Path exists:', require('fs').existsSync(PYTHON_PATH));

    writeLog('Starting Django server...');
    writeLog(`isDev: ${isDev}`);
    writeLog(`Django Path: ${DJANGO_PATH}`);
    writeLog(`Python Path: ${PYTHON_PATH}`);
    writeLog(`Django Path exists: ${fs.existsSync(DJANGO_PATH)}`);
    writeLog(`Python Path exists: ${fs.existsSync(PYTHON_PATH)}`);

    const SETTINGS_MODULE = 'config.settings.base';
    
    // Fixed: Use djangoProcess (not debugProcess) and clean up the Python command
    djangoProcess = spawn(PYTHON_PATH, [
        '-c',
        `
import sys
import os

# Add Django project directory to Python path
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Start Django server
from django.core.management import execute_from_command_line
execute_from_command_line(['manage.py', 'runserver', '8000', '--noreload', '--settings=${SETTINGS_MODULE}'])
        `
    ], {
        cwd: DJANGO_PATH,
        stdio: 'pipe'
    });
    
    djangoProcess.stdout.on('data', (data) => {
        console.log(`Django: ${data}`);
    });
    
    djangoProcess.stderr.on('data', (data) => {
        writeLog(`Django Error: ${data}`);
        console.log(`Django Error: ${data}`);
    });

    djangoProcess.on('error', (error) => {
        updateLoadingStatus(`Error starting application server: ${error}`);
        writeLog(`Failed to start Django: ${error}`);
        console.error('Failed to start Django:', error);
    });

    djangoProcess.on('exit', (code) => {
        console.log(`Django process exited with code ${code}`);
        if (code !== 0) {
            updateLoadingStatus('Application server stopped unexpectedly');
        }
    });
}

function stopDjango() {
    if (djangoProcess) {
        console.log('Stopping Django server...');
        djangoProcess.kill();
        djangoProcess = null;
    }
}

function createLoadingPage() {
    const loadingHTML = `
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ranch Tools - Loading</title>
        <style>
            body {
                margin: 0;
                padding: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                color: white;
            }
            .loading-container {
                text-align: center;
                background: rgba(255,255,255,0.1);
                padding: 40px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            }
            .spinner {
                border: 4px solid rgba(255,255,255,0.3);
                border-top: 4px solid white;
                border-radius: 50%;
                width: 50px;
                height: 50px;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            h1 {
                margin: 0 0 20px 0;
                font-size: 28px;
                font-weight: 300;
            }
            #status {
                font-size: 16px;
                opacity: 0.9;
                margin-top: 15px;
            }
        </style>
    </head>
    <body>
        <div class="loading-container">
            <div class="spinner"></div>
            <h1>Ranch Tools</h1>
            <div id="status">Initializing application...</div>
        </div>
    </body>
    </html>
    `;
    
    return `data:text/html;charset=utf-8,${encodeURIComponent(loadingHTML)}`;
}

function createWindow() {
    startDjango();

    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
        },
        icon: path.join(__dirname, 'icon.png'),
    });

    // Show loading page immediately
    mainWindow.loadURL(createLoadingPage());

    // Wait for Django to be ready
    waitForDjango(() => {
        mainWindow.loadURL('http://localhost:8000/database-management');
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

app.whenReady().then(createWindow);


// IPC handler for file save dialog
ipcMain.handle('show-save-dialog', async (event, options) => {
    const result = await dialog.showSaveDialog(mainWindow, options);
    return result;
});


app.on('window-all-closed', () => {
    stopDjango();
    app.quit();
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

app.on('before-quit', () => {
    stopDjango();
});
