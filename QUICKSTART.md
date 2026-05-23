# SwiftPDF Quick Start Guide

## 5-Minute Setup

### Windows (PowerShell)

```powershell
# 1. Navigate to project directory
cd C:\SwiftPDF

# 2. Create virtual environment
python -m venv .venv

# 3. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install -e .

# 5. Start the application
swiftpdf-ui
```

Visit: http://127.0.0.1:5000

### macOS/Linux

```bash
# 1. Navigate to project directory
cd ~/SwiftPDF

# 2. Create virtual environment
python3 -m venv .venv

# 3. Activate virtual environment
source .venv/bin/activate

# 4. Install dependencies
pip install -e .

# 5. Start the application
swiftpdf-ui
```

Visit: http://127.0.0.1:5000

## First Time Setup

### Step 1: Create Account
1. Click "Register" link
2. Enter name and email
3. Create password
4. Click "Register"

### Step 2: Login
1. Enter email and password
2. Click "Login"

### Step 3: Try Features
1. Select a tool from the grid
2. Upload file(s)
3. Configure options
4. Click action button
5. Download result

## Features Overview

### ✅ Already Implemented
- **Unlock PDF** - Remove password protection
- **Split PDF** - Extract specific pages
- **Merge PDF** - Combine multiple PDFs
- **Compress PDF** - Reduce file size
- **PDF to Word** - Convert to .docx
- **PDF to Excel** - Extract tables
- **PDF to PowerPoint** - Create slides
- **Office to PDF** - Convert DOCX/XLSX/PPTX
- **PDF to Images** - Export as JPG
- **Images to PDF** - Create PDF from images
- **Rotate PDF** - Rotate pages
- **Delete Pages** - Remove pages

## Troubleshooting

### "ModuleNotFoundError"
```bash
# Make sure virtual environment is activated
# Windows: .\.venv\Scripts\Activate.ps1
# Mac/Linux: source .venv/bin/activate

# Reinstall dependencies
pip install -e .
```

### "Port 5000 already in use"
```bash
# Use different port
swiftpdf-ui --port 8000
```

Visit: http://127.0.0.1:8000

### "LibreOffice not found" (for Office to PDF)
```bash
# Install LibreOffice

# Windows: Download from https://www.libreoffice.org/download/
# Mac: brew install libreoffice
# Linux: sudo apt-get install libreoffice
```

### "Permission denied" (Mac/Linux)
```bash
chmod +x .venv/bin/swiftpdf-ui
```

## Next Steps

1. **Explore Features** - Try each tool with sample PDFs
2. **Read Documentation** - Check [README.md](README.md)
3. **Configure** - Copy `.env.example` to `.env` for production
4. **Deploy** - Follow [DEPLOYMENT.md](DEPLOYMENT.md) for production
5. **Integrate** - Use CLI for scripting and automation

## Common Tasks

### Unlock a PDF via CLI
```bash
swiftpdf locked.pdf -o unlocked.pdf
```

### Split a PDF via CLI
```bash
swiftpdf input.pdf -o output.pdf --pages 1-5,10-15
```

### Batch Processing
Run multiple operations:
```bash
for file in *.pdf; do
  swiftpdf "$file" -o "unlocked_$file"
done
```

## Configuration

### Environment Variables
Create `.env` file:
```
SWIFTPDF_SECRET_KEY=your-secret-key
MAX_CONTENT_LENGTH=104857600
TEMP_DIR=/tmp/swiftpdf
```

See `.env.example` for all options.

## Docker Setup

### Quick Docker Run
```bash
docker build -t swiftpdf .
docker run -p 5000:5000 swiftpdf
```

### Docker Compose
```bash
docker-compose up -d
```

## Getting Help

### Check Logs
```bash
# Recent errors
tail -f logs/swiftpdf.log
```

### Debug Mode
```bash
# Set environment
export FLASK_ENV=development
export FLASK_DEBUG=1

# Run application
swiftpdf-ui
```

### Test Features
Visit: http://127.0.0.1:5000/register (if not logged in)

## Performance Tips

1. **Large Files**: Use compression first
2. **Batch Jobs**: Split into smaller files
3. **Temporary Space**: Ensure 5GB+ free disk
4. **Memory**: Close other applications
5. **Network**: Upload locally faster

## Security Notes

1. **Change Secret Key** in production
2. **Enable HTTPS** for remote access
3. **Use Firewall** to restrict access
4. **Regular Backups** of user database
5. **Keep Updated** - Regular security updates

## File Format Support

### Input Formats
- PDF: All versions
- DOCX/DOC: Microsoft Word
- XLSX/XLS: Microsoft Excel
- PPTX/PPT: Microsoft PowerPoint
- JPG/PNG/GIF/BMP: Images

### Output Formats
- PDF: All operations
- DOCX: PDF to Word
- XLSX: PDF to Excel
- PPTX: PDF to PowerPoint
- JPG: PDF to Images
- ZIP: Image archives

## Performance Expectations

| Operation | Time (approx) |
|-----------|---------------|
| Unlock 50MB PDF | <1s |
| Split PDF | 2-3s |
| Merge 2x50MB | 5-7s |
| Compress PDF | 10-15s |
| PDF to Word | 5-10s |
| PDF to Excel | 3-5s |
| PDF to PowerPoint | 8-12s |
| PDF to Images | 15-20s |

*Times vary based on file complexity and system resources*

## Additional Resources

- [README.md](README.md) - Full documentation
- [SETUP.md](SETUP.md) - Detailed setup guide
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment
- [ENHANCEMENTS.md](ENHANCEMENTS.md) - What's new
- [.env.example](.env.example) - Configuration template

## Support

For issues:
1. Check troubleshooting above
2. Review log files
3. Read documentation
4. Check system resources
5. Verify dependencies installed

## License

See LICENSE file for licensing information.

---

**Ready to get started?**

Run: `swiftpdf-ui` and visit http://127.0.0.1:5000

Enjoy SwiftPDF! 🚀
