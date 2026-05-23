# SwiftPDF - Professional PDF Tools Suite

SwiftPDF is a comprehensive, production-ready PDF processing application that supports an extensive range of PDF operations including unlock, merge, split, compress, format conversion, and editing capabilities.

**Supported Operations:**
- 🔓 **Unlock PDF** - Remove password protection
- 🔀 **Merge PDF** - Combine multiple PDFs
- ✂️ **Split PDF** - Extract pages by range
- 📦 **Compress PDF** - Reduce file size  
- 📄 **PDF to Word** - Convert to .docx
- 📊 **PDF to Excel** - Extract tables to .xlsx
- 🎯 **PDF to PowerPoint** - Convert pages to slides
- 🖼️ **PDF to Images** - Export as JPG files
- 📸 **Images to PDF** - Combine images
- 🔄 **Office to PDF** - Convert DOCX/XLSX/PPTX
- 🔁 **Rotate PDF** - Adjust page orientation
- 🗑️ **Delete Pages** - Remove unwanted pages

## Quick Start

### Prerequisites
- Python 3.9+
- LibreOffice (for Office document conversion)
- pip/conda for package management

### Installation

**Using pip:**
```bash
git clone <repository-url>
cd SwiftPDF
python -m venv .venv

# Windows
.\.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -e .
```

**Using conda:**
```bash
conda create -n swiftpdf python=3.11
conda activate swiftpdf
pip install -e .
```

### Running the Web UI

```bash
swiftpdf-ui
```

Then open: http://127.0.0.1:5000

### Restarting the Web UI

If you need to restart the running app, stop the process listening on port `5000` and then start the server again.

**Windows PowerShell**
```powershell
Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m SwiftPDF.web" -WorkingDirectory "$PWD" -NoNewWindow
```

**macOS/Linux**
```bash
pkill -f "python.*SwiftPDF.web" || true
python -m SwiftPDF.web
```

Then open: http://127.0.0.1:5000

### Command Line Usage

Unlock a PDF:
```bash
swiftpdf locked.pdf -o unlocked.pdf
```

Split a PDF:
```bash
swiftpdf locked.pdf -o output.pdf --pages 1-3,5
```

## Features

### PDF Operations

#### Unlock/Decrypt
- Remove password protection from encrypted PDFs
- Supports AES and RC4 encryption
- Secure password handling

#### Merge
- Combine multiple PDFs in order
- Preserve formatting and quality
- Support for large PDFs

#### Split
- Extract pages by range (e.g., 1-3,5,8-10)
- Maintain PDF quality
- Batch operations support

#### Compress
- Three compression levels: Low, Medium, High
- Intelligent image optimization
- Font subsetting for file size reduction

#### Format Conversion
- **PDF → Word (.docx)** with formatting preservation
- **PDF → Excel (.xlsx)** with table extraction
- **PDF → PowerPoint (.pptx)** with page-to-slide conversion
- **PDF → Images (.jpg)** with configurable DPI
- **Images → PDF** combining multiple images
- **Office → PDF** supporting DOCX, XLSX, PPTX

#### PDF Editing
- Rotate pages (90°, 180°, 270°, -90°)
- Delete specific pages or ranges
- Reorder pages

## Architecture

### Backend
- **Flask** - Web framework
- **pypdf** - PDF manipulation
- **PyMuPDF (fitz)** - Advanced PDF operations
- **pdf2docx** - PDF to Word conversion
- **python-pptx** - PowerPoint generation
- **Pillow** - Image processing
- **camelot-py** - Table extraction
- **LibreOffice** - Office document processing

### Frontend
- Responsive HTML/CSS/JavaScript
- Modern UI with tool cards
- Real-time progress updates
- Error handling and validation
- Multi-file upload support
- Drag-and-drop ready

### Database
- SQLite for user management
- Session-based authentication
- Secure password hashing

## Configuration

### Environment Variables

```bash
# Flask configuration
FLASK_ENV=production
SECRET_KEY=your-secret-key-here

# File upload settings
MAX_CONTENT_LENGTH=104857600  # 100MB max file size

# Processing settings
PDF_DPI_DEFAULT=150
PDF_DPI_MAX=300
```

### Configuration File

Create a `.env` file in the root directory:
```
SWIFTPDF_SECRET_KEY=your-production-secret-key
MAX_CONTENT_LENGTH=104857600
```

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libreoffice \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install -e .

EXPOSE 5000

CMD ["swiftpdf-ui", "--host", "0.0.0.0", "--port", "5000"]
```

### Production Deployment

1. **Install system dependencies:**
```bash
sudo apt-get install libreoffice
```

2. **Setup Python environment:**
```bash
python -m venv /opt/swiftpdf/venv
source /opt/swiftpdf/venv/bin/activate
pip install -e /opt/swiftpdf
```

3. **Configure systemd service:**
```ini
[Unit]
Description=SwiftPDF Web Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/swiftpdf
ExecStart=/opt/swiftpdf/venv/bin/swiftpdf-ui --host 0.0.0.0 --port 5000
Restart=always
Environment="SWIFTPDF_SECRET_KEY=your-secret-key"

[Install]
WantedBy=multi-user.target
```

4. **Setup Nginx reverse proxy:**
```nginx
upstream swiftpdf {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name pdf.example.com;

    client_max_body_size 100M;

    location / {
        proxy_pass http://swiftpdf;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Performance

### Optimization Features
- Streaming uploads for large files
- Temporary file cleanup
- Memory-efficient processing
- Parallel processing support
- Queue-based background jobs (configurable)

### File Size Support
- Tested with PDFs up to 500MB
- Configurable memory limits
- Automatic cleanup of temporary files
- Timeout handling for long-running operations

### Concurrency
- Multi-threaded request handling
- User session isolation
- Safe temporary file management
- Rate limiting ready

## Security

### Features
- User authentication with secure password hashing
- Session management
- MIME type validation
- File size validation
- Secure temporary file handling
- Input sanitization
- CSRF protection ready

### Best Practices
1. Use strong SECRET_KEY in production
2. Enable HTTPS/TLS
3. Set appropriate MAX_CONTENT_LENGTH
4. Use firewall for access control
5. Regular security updates
6. Monitor temporary file cleanup

## API Documentation

### Authentication
All endpoints require user login.

### Endpoints

**POST /unlock**
- Upload: `pdf` (file), `password` (string)
- Response: PDF file download

**POST /merge**
- Upload: `pdfs` (multiple files)
- Response: PDF file download

**POST /split**
- Upload: `pdf` (file), `page_ranges` (string, e.g., "1-3,5")
- Response: PDF file download

**POST /compress**
- Upload: `pdf` (file), `level` (low|medium|high)
- Response: PDF file download

**POST /pdf-to-word**
- Upload: `pdf` (file)
- Response: DOCX file download

**POST /pdf-to-powerpoint**
- Upload: `pdf` (file)
- Response: PPTX file download

**POST /pdf-to-excel**
- Upload: `pdf` (file)
- Response: XLSX file download

**POST /pdf-to-images**
- Upload: `pdf` (file), `dpi` (72-300, default: 150)
- Response: ZIP file with JPG images

**POST /images-to-pdf**
- Upload: `images` (multiple image files)
- Response: PDF file download

**POST /office-to-pdf**
- Upload: `document` (DOCX|DOC|XLSX|XLS|PPTX|PPT)
- Response: PDF file download

**POST /rotate-pdf**
- Upload: `pdf` (file), `page_ranges` (optional), `angle` (90|180|270|-90)
- Response: PDF file download

**POST /delete-pdf-pages**
- Upload: `pdf` (file), `page_ranges` (string)
- Response: PDF file download

## Troubleshooting

### LibreOffice Not Found
```bash
# Linux
sudo apt-get install libreoffice

# macOS
brew install libreoffice

# Windows
Download from https://www.libreoffice.org/download/
```

### PDF Conversion Issues
- Check file format compatibility
- Verify file is not corrupted
- Check available disk space
- Review application logs

### Performance Issues
- Monitor temporary file directory
- Check system memory availability
- Verify disk I/O performance
- Consider batch processing for multiple files

### Large File Handling
- Increase MAX_CONTENT_LENGTH if needed
- Monitor server resources
- Implement job queue for very large files
- Configure timeout appropriately

## Development

### Project Structure
```
SwiftPDF/
├── src/
│   └── SwiftPDF/
│       ├── __init__.py
│       ├── core.py          # PDF processing functions
│       ├── web.py           # Flask routes
│       ├── auth.py          # Authentication
│       ├── cli.py           # Command-line interface
│       ├── static/
│       │   ├── app.js       # Frontend logic
│       │   └── styles.css   # Styling
│       ├── templates/
│       │   ├── index.html   # Main UI
│       │   ├── login.html   # Auth
│       │   └── register.html
│       └── instance/        # Runtime data
├── tests/
│   ├── test_core.py
│   └── test_cli.py
├── pyproject.toml           # Project config
└── README.md
```

### Running Tests
```bash
pytest tests/
```

### Adding New Features
1. Add processing function to `core.py`
2. Add route to `web.py`
3. Add UI elements to templates
4. Update CSS if needed
5. Add tests to verify functionality

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

[Specify your license here]

## Support

For issues, feature requests, or support:
- Open an issue on GitHub
- Check documentation
- Review troubleshooting guide

## Changelog

### Version 0.2.0
- ✨ Added Merge PDF
- ✨ Added Compress PDF
- ✨ Added PDF to Word/PowerPoint/Excel conversion
- ✨ Added Office to PDF conversion
- ✨ Added PDF to Images/Images to PDF
- ✨ Added PDF editing (rotate, delete pages)
- 🎨 Enhanced UI with responsive grid
- 📚 Comprehensive documentation

### Version 0.1.0
- Initial release
- Unlock PDF
- Split PDF


Install test dependencies:

```powershell
python -m pip install -e . pytest
```

Run tests:

```powershell
pytest
```
