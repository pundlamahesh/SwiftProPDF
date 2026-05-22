# SwiftPDF

SwiftPDF is a fast and secure PDF tools suite that includes unlock, split, and merge capabilities. Get started with unlocking password-protected PDFs when you know the password.

Use it only for PDFs you own or are authorized to unlock.

## Setup

```powershell
cd SwiftPDF
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Usage

Unlock one PDF:

```powershell
swiftpdf locked.pdf -p "your-password" -o unlocked.pdf
```

Prompt for the password instead of putting it in the command:

```powershell
swiftpdf locked.pdf -o unlocked.pdf
```

Overwrite the output file if it already exists:

```powershell
swiftpdf locked.pdf -o unlocked.pdf --overwrite
```

## Web UI

Start the SwiftPDF web app:

```powershell
swiftpdf-ui
```

Open:

```text
http://127.0.0.1:5000
```

## Development

Install test dependencies:

```powershell
python -m pip install -e . pytest
```

Run tests:

```powershell
pytest
```
