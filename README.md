![PaperAtlas Banner](banner.png)

# PaperAtlas

A single-step web app to pull your Scholar Inbox preferences, annotate all papers and authors of interest from any conference with LLMs, generate a synthesis, and produce a summary website.

https://github.com/user-attachments/assets/3f7a0b74-1a21-4fdd-a361-3ea0073d6e2d

## Quick Start

1. Clone and run:
```bash
git clone https://github.com/aldro61/PaperAtlas.git
cd PaperAtlas
chmod +x run.sh
OPENROUTER_API_KEY="your-key" ./run.sh
```

2. In the browser:
   - Paste your Scholar Inbox secret login link
   - Pick the conference
   - Click Start

## Requirements

- Python 3.9+
- `OPENROUTER_API_KEY` (get one at [OpenRouter](https://openrouter.ai))
- Scholar Inbox account with scored conferences

## License

Apache 2.0
