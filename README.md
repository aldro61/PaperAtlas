![PaperAtlas Banner](banner.png)

# PaperAtlas

A pipeline for generating a personalized conference summary website with AI-powered paper analysis, author enrichment, and research synthesis.

> **Note**: This is a quick project I hacked together to understand the landscape of papers and authors that fit my interests at NeurIPS 2025. I am not actively maintaining it but would be very happy to receive pull requests if someone wants to take this further. The `example/` directory contains sample outputs from my NeurIPS 2025 analysis.

## Overview

This tool helps you navigate large academic conferences by:
- Analyzing papers based on your research interests
- Enriching papers with key findings, novelty assessments, and category tags
- Identifying key authors to meet with institutional affiliations
- Generating a comprehensive research synthesis with interactive paper references
- Creating a beautiful, professional website to explore all this information

## Prerequisites

- Python 3.7+
- [Claude CLI](https://github.com/anthropics/claude-code) installed and configured with your API key
- A Scholar Inbox account with conference papers scored (scholar-inbox.com)

## Initial Setup

### 1. Download Your Conference Data

1. Go to [scholar-inbox.com](https://scholar-inbox.com) and navigate to your conference page
2. **Important**: Manually expand all poster sessions (click all "Show more" buttons)
3. Save the entire page as MHTML:
   - Chrome/Edge: Right-click → "Save as..." → Format: "Webpage, Single File (*.mhtml)"
   - The saved file contains all paper data with your relevance scores
4. Rename the saved file to `conference.mhtml` and place it in this directory

### 2. Extract Paper Data

Run the extraction script:

```bash
python scrape_scholar_inbox.py
```

**What it does**: Extracts paper information (titles, authors, scores, PDFs) from the MHTML file and creates `papers.csv` containing all papers with positive relevance scores.

**Output**: `papers.csv`

## Quick Start

Once you have `conference.mhtml` in the repository directory, you can run the entire pipeline with a single command:

```bash
bash build.sh
```

This will execute all steps sequentially: extraction → paper enrichment → author enrichment → synthesis → website generation.

Alternatively, follow the individual pipeline steps below for more control.

## Pipeline Steps

### Step 1: Enrich Papers with AI Analysis

```bash
python enrich_papers.py
```

**What it does**:
- Reads PDFs for each paper (or falls back to titles for papers without PDFs)
- Uses Claude to analyze each paper and extract:
  - Key findings and insights
  - Novelty assessment (what makes it different from prior work)
  - Main contribution
  - Research categories (automatically generated across all papers)
- Creates enriched paper data with skip logic (won't re-process already enriched papers)

**Time**: Varies by conference size (typically 10-20 minutes with 50 parallel workers)

**Output**: `enriched_papers.json`

**Configuration**:
- Adjust `max_workers` in the script for faster/slower processing
- Papers already enriched will be skipped on re-runs

### Step 2: Enrich Authors with Institutional Data

```bash
python enrich_authors.py
```

**What it does**:
- Identifies key authors (first, second, and last authors from papers scoring ≥85)
- Uses Claude to search for each author's:
  - Current institutional affiliation
  - Role/position
  - Photo (if available)
  - Profile URL
- Implements skip logic (won't re-enrich already processed authors)

**Time**: Varies by number of authors (typically 5-10 minutes with 15 parallel workers)

**Output**: `enriched_authors.json`

**Note**: Some authors may not be found (marked as "Unknown") - this is normal for authors with common names or limited online presence.

### Step 3: Generate Research Synthesis

```bash
python synthesize_conference.py
```

**What it does**:
- Analyzes all enriched papers to identify major trends, surprising findings, and connections
- Generates a comprehensive 2000-3000 word critical synthesis
- Creates interactive paper references with hover tooltips
- Includes a collapsible reference index at the bottom

**Time**: ~5-10 minutes (depending on number of papers)

**Output**: `conference_synthesis.html`

**Note**: The synthesis uses Claude CLI with a long context window to analyze all papers together.

### Step 4: Generate the Website

```bash
python generate_website.py
```

**What it does**:
- Combines all enriched data into a single-page application
- Creates interactive visualizations (score distributions, category charts)
- Builds sortable, filterable paper and author lists
- Embeds the research synthesis with working tooltips
- Generates a professional, modern website design

**Output**: `index.html`

**Open the website**: Simply open `index.html` in your web browser!

**Example**: You can preview the website format by opening `example/index.html` to see sample outputs from a NeurIPS 2025 analysis.

## Website Features

### Papers Tab
- View all papers with scores, categories, and summaries
- Sort by score or title
- Filter by research category
- Click papers to see detailed enrichment data
- Direct links to PDFs

### Authors Tab
- Browse key authors ranked by highly relevant papers (score ≥85)
- See institutional affiliations and roles
- View all papers by each author
- Institution breakdown chart
- Links to author profiles

### Synthesis Tab
- Read a comprehensive research synthesis
- Hover over paper references to see titles and details
- Expandable reference index with links to PDFs
- Professional formatting with clear sections

## File Structure

```
PaperAtlas/
├── scrape_scholar_inbox.py        # Extract data from MHTML
├── enrich_papers.py               # AI-powered paper analysis
├── enrich_authors.py              # Author institutional lookup
├── synthesize_conference.py       # Generate research synthesis
├── generate_website.py            # Build final website
├── build.sh                       # One-command pipeline runner
├── banner.png                     # Repository banner image
├── example/                       # Sample outputs from NeurIPS 2025
│   ├── papers.csv                 #   Example extracted papers
│   ├── enriched_authors.json      #   Example enriched authors
│   ├── enriched_papers.json       #   Example enriched papers
│   ├── conference_synthesis.html  #   Example synthesis
│   └── index.html                 #   Example final website
│
# Files you'll generate when running the pipeline:
├── conference.mhtml               # Your downloaded conference data
├── papers.csv                     # Extracted paper data
├── enriched_papers.json           # Your papers with AI analysis
├── enriched_authors.json          # Your authors with affiliations
├── conference_synthesis.html      # Your research synthesis
├── conference_synthesis.md        # Markdown version of synthesis
└── index.html                     # Your final website
```

## Configuration & Customization

### Adjusting the Relevance Threshold

The default threshold for "highly relevant" papers is **85**. To change it:

1. Edit the threshold in both `enrich_authors.py` and `generate_website.py`
2. Look for lines with `score >= 85` and update to your preferred value
3. Re-run the affected scripts

### Author Selection Criteria

By default, the pipeline considers **first, second, and last authors** from highly relevant papers. This captures:
- Primary contributors (first author)
- Key collaborators (second author)
- Senior researchers/PIs (last author)

### Parallel Processing

Adjust the `max_workers` parameter in scripts for your needs:
- **enrich_papers.py**: Default 50 workers (decrease if hitting rate limits)
- **enrich_authors.py**: Default 15 workers (more conservative due to web searches)

### Synthesis Prompt

To customize the synthesis style or focus, edit the prompt in `synthesize_conference.py` around line 52.

## Troubleshooting

### "Invalid API key" errors
- Ensure Claude CLI is properly configured: `claude doctor`
- Check your API key: `echo $ANTHROPIC_API_KEY`

### Papers not enriching
- Check if PDFs are accessible (some may be behind paywalls)
- The script will fall back to title-only analysis for inaccessible PDFs
- Check console output for specific error messages

### Authors showing as "Unknown"
- Common for authors with generic names or limited web presence
- The script will still include them but without institutional details
- You can manually update `enriched_authors.json` if needed

### Website synthesis not showing
- Ensure `conference_synthesis.html` exists
- Check that tooltips are working (paper references should be interactive)
- Regenerate with `python synthesize_conference.py` if needed

## Re-running the Pipeline

All scripts implement **skip logic**:
- **enrich_papers.py**: Only processes papers without complete enrichment
- **enrich_authors.py**: Skips authors already fully enriched
- **synthesize_conference.py**: Overwrites synthesis (re-run to update)
- **generate_website.py**: Always regenerates (fast, no API calls)

To force complete re-enrichment, delete the relevant JSON files before running.

## Tips for Best Results

1. **Expand all sessions** on Scholar Inbox before saving - collapsed sections won't be captured
2. **Review your scores** on Scholar Inbox first - the pipeline uses these scores throughout
3. **Run steps sequentially** - each step depends on the previous one's output
4. **Check enrichment quality** - spot-check a few papers/authors to ensure good results
5. **Regenerate synthesis** if you update paper enrichments - it pulls from enriched data
6. **Use the synthesis** - hover over paper references to quickly understand context

## Credits

Built with:
- [Claude CLI](https://github.com/anthropics/claude-code) for AI analysis
- [Chart.js](https://www.chartjs.org/) for visualizations
- [Scholar Inbox](https://scholar-inbox.com) for paper scoring and management

## License

MIT License - Feel free to adapt for your own conferences!
