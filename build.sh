#!/bin/bash

# Conference Helper - Build Script
# Runs all pipeline steps to generate index.html
# Prerequisites: MHTML file from Scholar Inbox must exist

set -e  # Exit on any error

echo "=========================================="
echo "Conference Helper - Build Pipeline"
echo "=========================================="
echo ""

# Check if the required MHTML file exists
if [ ! -f "neurips2025.mhtml" ]; then
    echo "Error: neurips2025.mhtml not found!"
    echo "Please download the conference page from Scholar Inbox as MHTML first."
    echo "See README.md for instructions."
    exit 1
fi

# Step 1: Extract Paper Data from MHTML
echo "[Step 1/5] Extracting paper data from MHTML..."
python scrape_neurips.py
echo "✓ Paper extraction complete."
echo ""

# Step 2: Enrich Papers with AI Analysis
echo "[Step 2/5] Enriching papers with AI analysis..."
echo "This may take 10-20 minutes for 300-400 papers."
python enrich_papers.py
echo "✓ Paper enrichment complete."
echo ""

# Step 3: Enrich Authors with Institutional Data
echo "[Step 3/5] Enriching authors with institutional data..."
echo "This may take 5-10 minutes for 50-150 authors."
python enrich_authors.py
echo "✓ Author enrichment complete."
echo ""

# Step 4: Generate Research Synthesis
echo "[Step 4/5] Generating research synthesis..."
echo "This may take 5-10 minutes."
python synthesize_conference.py
echo "✓ Research synthesis complete."
echo ""

# Step 5: Generate the Website
echo "[Step 5/5] Generating website..."
python generate_website.py
echo "✓ Website generation complete."
echo ""

echo "=========================================="
echo "Build complete!"
echo "Open index.html in your browser to view the website."
echo "=========================================="
