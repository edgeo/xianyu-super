#!/bin/bash
# Start Xvfb (Virtual Framebuffer) for Playwright
Xvfb :99 -screen 0 1280x1024x24 &
export DISPLAY=:99

# Run the python app
python Start.py
