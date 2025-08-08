#!/bin/bash
# Quick launcher script for the Automated Followspot System
# Makes the Python launcher executable and provides easy access

# Make the launcher scripts executable
chmod +x launcher.py
chmod +x launcher_gui.py
chmod +x setup.py

# Create a simple alias script
cat > followspot << 'EOF'
#!/bin/bash
# Automated Followspot System Launcher Alias
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
python3 "$SCRIPT_DIR/launcher.py" "$@"
EOF

chmod +x followspot

echo "🎬 Automated Followspot System Setup Complete!"
echo ""
echo "Available commands:"
echo "  ./followspot                # Launch GUI interface (default)"
echo "  ./followspot --cli          # Launch CLI interface"
echo "  ./followspot --status       # Show system status"
echo "  ./followspot --demo         # Run demo mode"
echo "  ./followspot --configure    # Configure cameras"
echo "  python setup.py             # Install dependencies"
echo "  python launcher.py --help   # Show all options"
echo ""
echo "Recommended first step: ./followspot (launches GUI by default)"
