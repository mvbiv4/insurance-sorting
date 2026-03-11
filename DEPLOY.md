# Deployment Guide - Insurance Requisition Sorting System

This system processes scanned insurance requisitions using OCR, checks them against a blocklist, and provides a web dashboard for staff to review flagged cases.

There are two deployment methods. Choose whichever fits your environment.

---

## Prerequisites

### Both Methods
- Insurance blocklist CSV file (provided by CPG compliance team)
- Network path or local folder where scanned requisitions land

### Method 1: Docker
- Docker Desktop for Windows (or Docker Engine on Linux)
- Docker Compose v2+

### Method 2: Portable Windows
- Python 3.10 or later — https://www.python.org/downloads/
  - **Check "Add Python to PATH"** during installation
- Tesseract OCR — install via one of:
  - Scoop: `scoop install tesseract`
  - Manual installer: https://github.com/UB-Mannheim/tesseract/wiki
  - Install to `C:\Program Files\Tesseract-OCR\` (default)
- Internet access during initial setup (to download Python packages)

---

## Method 1: Docker

### Setup

```bash
# Clone or copy the project to the target machine
cd insurance-sorting

# Create a .env file to configure the scan folder path
echo SCAN_FOLDER=\\\\server\share\scans > .env

# Place your blocklist in the config directory
copy your_blocklist.csv config\insurance_blocklist.csv

# Build and start
docker-compose up -d
```

### What It Runs
- **Web dashboard** on port 5000 — staff open http://localhost:5000 in a browser
- **Folder watcher** — monitors the configured scan folder for new files

### Management
```bash
# View logs
docker-compose logs -f

# Stop
docker-compose down

# Restart after config changes
docker-compose restart

# Rebuild after code updates
docker-compose up -d --build
```

---

## Method 2: Portable Windows (No Docker)

### Initial Setup

1. Open a Command Prompt and navigate to the project folder:
   ```
   cd C:\path\to\insurance-sorting
   ```

2. Run the setup script:
   ```
   deploy\setup.bat
   ```
   This will:
   - Verify Python 3.10+ and Tesseract are installed
   - Create a Python virtual environment
   - Install all dependencies
   - Create necessary data directories

3. Place your blocklist file:
   ```
   copy your_blocklist.csv config\insurance_blocklist.csv
   ```

### Starting the System

Open **two** Command Prompt windows:

**Window 1 — Web Dashboard:**
```
deploy\start-web.bat
```

**Window 2 — Folder Watcher:**
```
deploy\start-watcher.bat \\server\share\scans
```

If no folder argument is given, the watcher defaults to the `scans\` directory inside the project.

Then open a browser to **http://localhost:5000**.

### Installing as Windows Services (Optional)

To run the system automatically on boot without needing to keep terminal windows open:

1. Install NSSM (Non-Sucking Service Manager):
   ```
   scoop install nssm
   ```
   Or download from https://nssm.cc/download and add to PATH.

2. Run the service installer **as Administrator**:
   ```
   deploy\install-service.bat \\server\share\scans
   ```

This installs two services:
- **InsuranceSortingWeb** — web dashboard on port 5000
- **InsuranceSortingWatcher** — monitors the scan folder

Both are set to auto-start on boot and restart automatically on failure.

### Health Check

Run at any time to verify the system is working:
```
deploy\check-health.bat
```

This checks:
- Web dashboard is responding
- Watcher process is running
- Database exists
- Blocklist config is present
- Disk space is adequate
- Tesseract is installed

---

## Configuration

### Blocklist File
Place your insurance blocklist CSV at:
```
config\insurance_blocklist.csv
```

The system watches this file — updates take effect when the next scan is processed.

### Scan Folder
- **Docker:** Set `SCAN_FOLDER` in the `.env` file
- **Portable:** Pass the path as an argument to `start-watcher.bat` or `install-service.bat`

UNC paths (e.g., `\\server\share\scans`) are supported. The machine must have read access to the share.

---

## Verifying It Works

1. Open http://localhost:5000 — you should see the dashboard with zero cases
2. Drop a test scan (PDF, TIFF, or image) into the watched folder
3. Within a few seconds, it should appear on the dashboard
4. Check the status: flagged, clear, needs_review, or poor_scan

If a scan shows "poor_scan" with an orange banner, the image quality was too low for reliable OCR. Re-scan at higher resolution (300 DPI minimum).

---

## Troubleshooting

### Web dashboard won't start
- Check port 5000 is not in use: `netstat -an | findstr :5000`
- Check logs in `logs\web-service.log` (if running as service)
- Run `deploy\start-web.bat` manually to see error output

### Watcher not picking up files
- Verify the scan folder path is correct and accessible
- Check the watcher is running: `deploy\check-health.bat`
- Supported formats: PDF, TIFF, TIF, PNG, JPG, JPEG, BMP
- Files must be new — already-processed files are tracked in the database

### OCR quality is poor
- Scan at 300 DPI or higher, black and white mode
- Ensure scans are not skewed or cut off
- Poor-quality scans are auto-flagged with a "poor_scan" status

### "Tesseract not found" errors
- Verify Tesseract is installed: `tesseract --version`
- If installed via Scoop, make sure your PATH includes the Scoop shims directory
- Restart your terminal after installing Tesseract

### Database locked errors
- This can happen if multiple processes write simultaneously
- The system uses WAL mode and a 30-second busy timeout to minimize this
- If persistent, check that only one watcher instance is running

### Service won't start
- Check logs: `logs\web-service-error.log` and `logs\watcher-service-error.log`
- Verify with: `nssm status InsuranceSortingWeb`
- Try running the bat scripts manually first to rule out environment issues

---

## Updating the Application

### Docker
```bash
# Pull latest code, then rebuild
docker-compose up -d --build
```

### Portable Windows
```bash
# Pull latest code, then re-run setup to update dependencies
deploy\setup.bat
```

The setup script is safe to re-run — it will skip steps that are already done and update packages as needed.

Data in the `data\`, `config\`, and `reports\` directories is preserved across updates.
