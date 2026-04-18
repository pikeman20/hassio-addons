#!/bin/bash
# CUPS Printer Setup Helper
# Configures CUPS for Scan Agent printing

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}CUPS Printer Setup${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (sudo)${NC}" 
   exit 1
fi

# Check if CUPS is installed
if ! command -v lpstat &> /dev/null; then
    echo -e "${RED}CUPS not installed. Installing...${NC}"
    apt-get update
    apt-get install -y cups cups-client
fi

# Start CUPS service
echo -e "${YELLOW}Starting CUPS service...${NC}"
systemctl enable cups
systemctl start cups

# Check CUPS status
if systemctl is-active --quiet cups; then
    echo -e "${GREEN}CUPS is running${NC}"
else
    echo -e "${RED}Failed to start CUPS${NC}"
    exit 1
fi

# List available printers
echo ""
echo -e "${YELLOW}Checking for available printers...${NC}"
lpstat -p -d

# Detect network printers
echo ""
echo -e "${YELLOW}Detecting network printers (this may take a moment)...${NC}"
lpinfo -v | grep -i "network\|socket\|ipp"

echo ""
echo -e "${YELLOW}Printer Setup Options:${NC}"
echo "1) Auto-detect and add printers"
echo "2) Manually add a printer"
echo "3) Configure existing printer"
echo "4) Set default printer"
echo "5) Test print"
echo "6) Exit"
read -p "Enter choice [1-6]: " CHOICE

case $CHOICE in
    1)
        echo -e "${YELLOW}Auto-detecting printers...${NC}"
        
        # Brother printer detection (common for home users)
        if lpinfo -v | grep -i "brother"; then
            echo -e "${GREEN}Found Brother printer(s)${NC}"
            # Show detected printers
            lpinfo -v | grep -i "brother"
        fi
        
        # HP printer detection
        if lpinfo -v | grep -i "hp"; then
            echo -e "${GREEN}Found HP printer(s)${NC}"
            lpinfo -v | grep -i "hp"
        fi
        
        echo ""
        echo -e "${YELLOW}Please use option 2 to manually add your printer${NC}"
        ;;
        
    2)
        echo ""
        echo "Manual Printer Addition"
        echo "----------------------"
        read -p "Enter printer name (e.g., Brother_HL_L2350DW): " PRINTER_NAME
        read -p "Enter printer URI (e.g., socket://192.168.1.100): " PRINTER_URI
        
        echo ""
        echo "Select printer driver:"
        echo "1) Brother HL-L2350DW (Generic PCL)"
        echo "2) HP LaserJet (Generic PCL)"
        echo "3) Generic PostScript"
        echo "4) Other (specify PPD file)"
        read -p "Enter choice [1-4]: " DRIVER_CHOICE
        
        case $DRIVER_CHOICE in
            1)
                PPD="drv:///sample.drv/generic-pcl6.ppd"
                ;;
            2)
                PPD="drv:///sample.drv/generic-pcl.ppd"
                ;;
            3)
                PPD="drv:///sample.drv/generic-ps.ppd"
                ;;
            4)
                read -p "Enter PPD file path: " PPD
                ;;
            *)
                echo -e "${RED}Invalid choice${NC}"
                exit 1
                ;;
        esac
        
        echo -e "${YELLOW}Adding printer...${NC}"
        lpadmin -p "$PRINTER_NAME" -v "$PRINTER_URI" -m "$PPD" -E
        
        # Enable printer
        cupsenable "$PRINTER_NAME"
        cupsaccept "$PRINTER_NAME"
        
        echo -e "${GREEN}Printer $PRINTER_NAME added successfully${NC}"
        
        # Set as default
        read -p "Set as default printer? (y/n): " SET_DEFAULT
        if [ "$SET_DEFAULT" == "y" ]; then
            lpadmin -d "$PRINTER_NAME"
            echo -e "${GREEN}$PRINTER_NAME set as default printer${NC}"
        fi
        ;;
        
    3)
        echo ""
        echo "Available printers:"
        lpstat -p -d
        echo ""
        read -p "Enter printer name to configure: " PRINTER_NAME
        
        if ! lpstat -p "$PRINTER_NAME" &> /dev/null; then
            echo -e "${RED}Printer $PRINTER_NAME not found${NC}"
            exit 1
        fi
        
        echo ""
        echo "Configuration options:"
        echo "1) Enable duplex (two-sided) printing"
        echo "2) Set monochrome as default"
        echo "3) Set paper size"
        echo "4) All of the above"
        read -p "Enter choice [1-4]: " CONFIG_CHOICE
        
        case $CONFIG_CHOICE in
            1|4)
                lpoptions -p "$PRINTER_NAME" -o sides=two-sided-long-edge
                echo -e "${GREEN}Duplex enabled${NC}"
                ;;&
            2|4)
                lpoptions -p "$PRINTER_NAME" -o print-color-mode=monochrome
                echo -e "${GREEN}Monochrome set as default${NC}"
                ;;&
            3|4)
                echo "Select paper size:"
                echo "1) A4"
                echo "2) Letter"
                read -p "Enter choice [1-2]: " PAPER_CHOICE
                
                if [ "$PAPER_CHOICE" == "1" ]; then
                    lpoptions -p "$PRINTER_NAME" -o media=A4
                    echo -e "${GREEN}Paper size set to A4${NC}"
                elif [ "$PAPER_CHOICE" == "2" ]; then
                    lpoptions -p "$PRINTER_NAME" -o media=Letter
                    echo -e "${GREEN}Paper size set to Letter${NC}"
                fi
                ;;
        esac
        
        echo -e "${GREEN}Printer configured${NC}"
        ;;
        
    4)
        echo ""
        echo "Available printers:"
        lpstat -p -d
        echo ""
        read -p "Enter printer name to set as default: " PRINTER_NAME
        
        lpadmin -d "$PRINTER_NAME"
        echo -e "${GREEN}$PRINTER_NAME set as default printer${NC}"
        ;;
        
    5)
        echo ""
        echo "Available printers:"
        lpstat -p -d
        echo ""
        read -p "Enter printer name to test: " PRINTER_NAME
        
        # Create test page
        echo "Scan Agent Test Print" > /tmp/test_print.txt
        echo "Timestamp: $(date)" >> /tmp/test_print.txt
        echo "Printer: $PRINTER_NAME" >> /tmp/test_print.txt
        
        echo -e "${YELLOW}Sending test print...${NC}"
        lp -d "$PRINTER_NAME" /tmp/test_print.txt
        
        rm /tmp/test_print.txt
        echo -e "${GREEN}Test print sent${NC}"
        ;;
        
    6)
        echo "Exiting..."
        exit 0
        ;;
        
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}CUPS setup complete!${NC}"
echo ""
echo "Useful commands:"
echo "  lpstat -p -d          # List printers and default"
echo "  lpstat -t             # Full printer status"
echo "  lpoptions -p <name>   # Show printer options"
echo "  lpadmin -p <name> -o <option>=<value>  # Set option"
echo "  lp -d <name> <file>   # Test print"
