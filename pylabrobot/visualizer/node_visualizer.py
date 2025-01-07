"""Headless visualizer that uses Node.js to render frames and create GIFs."""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
import inspect

from pylabrobot.resources import Resource
from .visualizer import Visualizer

# Create a dedicated logger for the visualizer
logger = logging.getLogger("pylabrobot.visualizer.node")

class NodeVisualizer(Visualizer):
    """A headless visualizer that uses Node.js to render frames and create GIFs.
    This reuses the existing JavaScript visualization code but runs it in Node instead of a browser.
    """

    def __init__(
        self,
        resource: Resource,
        output_dir: str = "visualization_frames",
        gif_path: str = "protocol.gif",
        frame_delay: int = 100,  # ms between frames
    ):
        """Create a new NodeVisualizer.

        Args:
            resource: The root resource to visualize
            output_dir: Directory to save visualization frames
            gif_path: Path to save the final GIF
            frame_delay: Milliseconds between frames in the GIF
        """
        # Configure logging for this instance
        self.logger = logging.getLogger("pylabrobot.visualizer.node")
        self.logger.info("Initializing NodeVisualizer...")
        
        super().__init__(
            resource=resource,
            ws_host="127.0.0.1",
            ws_port=2121,
            open_browser=False  # Never open browser
        )
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.gif_path = gif_path
        self.frame_delay = frame_delay
        self.frame_count = 0
        
        # Create temp directory for Node.js files
        self.temp_dir = Path(tempfile.mkdtemp())
        self._setup_node_environment()

        # Initialize event loop in setup() instead
        self._root_resource = resource

        # Register callbacks for liquid handling operations
        if hasattr(resource, 'register_callback'):
            for operation in [
                "pick_up_tips",
                "drop_tips",
                "aspirate",
                "dispense",
                "pick_up_tips96",
                "drop_tips96",
                "aspirate96",
                "dispense96"
            ]:
                resource.register_callback(operation, self._operation_callback)
        
        self.logger.info(f"NodeVisualizer initialized with output_dir={output_dir}, gif_path={gif_path}")

    async def _operation_callback(self, *args, **kwargs):
        """Callback for liquid handling operations."""
        # Get the operation name from the callback frame
        frame = inspect.currentframe()
        operation = frame.f_back.f_code.co_name
        self.logger.debug(f"Operation callback: {operation}")
        await self._capture_frame(f"operation_{operation}")

    async def _handle_resource_assigned_callback(self, resource: Resource):
        """Handle resource assignment by capturing a frame."""
        self.logger.debug(f"Resource assigned: {resource.name}")
        await self._capture_frame(f"assign_{resource.name}")

    async def _handle_resource_unassigned_callback(self, resource: Resource):
        """Handle resource unassignment by capturing a frame."""
        self.logger.debug(f"Resource unassigned: {resource.name}")
        await self._capture_frame(f"unassign_{resource.name}")

    async def _handle_state_update_callback(self, resource: Resource):
        """Handle state updates by capturing a frame."""
        self.logger.debug(f"State update: {resource.name}")
        await self._capture_frame(f"state_update_{resource.name}")

    async def setup(self):
        """Start the visualizer."""
        self.logger.info("Setting up Node visualizer...")
        await super().setup()
        
        # Create initial frame
        await self._capture_frame("initial_state")

    def _setup_node_environment(self):
        """Set up the Node.js environment with required files and dependencies."""
        self.logger.debug("Setting up Node.js environment...")
        
        # Copy required files to temp directory
        vis_dir = Path(__file__).parent
        self.logger.debug(f"Copying visualization files from {vis_dir}")
        for file in ['lib.js', 'gif.js', 'gif.worker.js']:
            try:
                with open(vis_dir / file, 'r') as f:
                    content = f.read()
                with open(self.temp_dir / file, 'w') as f:
                    f.write(content)
                self.logger.debug(f"Copied {file}")
            except Exception as e:
                self.logger.error(f"Failed to copy {file}: {e}")
                raise

        self.logger.debug(f"Creating Node.js script in {self.temp_dir}")
        # Create Node.js script for headless rendering
        node_script = """
        const { createCanvas } = require('canvas');
        const fs = require('fs');
        const GIFEncoder = require('gifencoder');
        const path = require('path');

        // Setup canvas with larger dimensions
        const canvas = createCanvas(2000, 1200);  
        const ctx = canvas.getContext('2d');

        // Create GIF encoder with larger dimensions
        const encoder = new GIFEncoder(2000, 1200);
        encoder.createReadStream().pipe(fs.createWriteStream(process.argv[2]));
        encoder.start();
        encoder.setRepeat(0);
        encoder.setDelay(parseInt(process.argv[3]));
        encoder.setQuality(10);

        // Colors and styles
        const COLORS = {
            DECK: '#5B6D8F',
            TIP_RACK: '#7B8CAF',
            TIP: '#2F3D5F',
            TIP_SPOT_EMPTY: '#FFFFFF',
            TIP_SPOT_BORDER: '#000000',
            PLATE: '#6B7C9F',
            WELL_EMPTY: '#FFFFFF',
            TROUGH: '#9BA8C7',
            COMPOUNDS: {
                'Compound A': '#FF4444',  // Red
                'Compound B': '#4444FF',  // Blue
                'Compound C': '#44FF44',  // Green
                'Compound D': '#FFFF44'   // Yellow
            }
        };

        // Function to draw a pie chart
        function drawPieChart(ctx, x, y, radius, data, maxVolume) {
            let total = data.reduce((sum, [_, volume]) => sum + volume, 0);
            if (total === 0) {
                ctx.fillStyle = COLORS.WELL_EMPTY;
                ctx.beginPath();
                ctx.arc(x, y, radius, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
                return;
            }

            let startAngle = 0;
            data.forEach(([compound, volume]) => {
                const sliceAngle = (volume / total) * Math.PI * 2;
                
                ctx.fillStyle = COLORS.COMPOUNDS[compound] || '#999999';
                ctx.beginPath();
                ctx.moveTo(x, y);
                ctx.arc(x, y, radius, startAngle, startAngle + sliceAngle);
                ctx.closePath();
                ctx.fill();
                ctx.stroke();
                
                startAngle += sliceAngle;
            });

            // Draw outline
            ctx.strokeStyle = '#000000';
            ctx.lineWidth = 2;  // Thicker outline
            ctx.beginPath();
            ctx.arc(x, y, radius, 0, Math.PI * 2);
            ctx.stroke();
            ctx.lineWidth = 1;  // Reset line width
        }

        // Function to draw a tip spot
        function drawTipSpot(ctx, x, y, width, height, hasTip) {
            // Draw tip spot background with more contrast
            ctx.fillStyle = hasTip ? COLORS.TIP : COLORS.TIP_SPOT_EMPTY;
            ctx.strokeStyle = hasTip ? '#000000' : '#CCCCCC';
            ctx.lineWidth = hasTip ? 2 : 1;
            
            // Draw as a rounded rectangle
            const radius = Math.min(width, height) * 0.2;
            ctx.beginPath();
            ctx.moveTo(x + radius, y);
            ctx.lineTo(x + width - radius, y);
            ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
            ctx.lineTo(x + width, y + height - radius);
            ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
            ctx.lineTo(x + radius, y + height);
            ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
            ctx.lineTo(x, y + radius);
            ctx.quadraticCurveTo(x, y, x + radius, y);
            ctx.closePath();
            
            ctx.fill();
            ctx.stroke();

            // If there's a tip, add more visible detail
            if (hasTip) {
                // Draw tip detail
                const tipWidth = width * 0.7;  // Wider tip
                const tipHeight = height * 0.9;  // Taller tip
                const tipX = x + (width - tipWidth) / 2;
                const tipY = y + (height - tipHeight) / 2;
                
                ctx.fillStyle = COLORS.TIP;
                ctx.beginPath();
                ctx.moveTo(tipX, tipY);
                ctx.lineTo(tipX + tipWidth, tipY);
                ctx.lineTo(tipX + tipWidth/2, tipY + tipHeight);
                ctx.closePath();
                ctx.fill();
                ctx.stroke();
            }
        }

        // Function to render a frame
        function renderFrame(state) {
            // Clear canvas
            ctx.clearRect(0, 0, 2000, 1200);
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, 2000, 1200);
            
            // Draw resources recursively
            function drawResource(resource) {
                // Use different scaling for different resource types
                let scale = 1.5;  // Default scale
                if (resource.type === 'Plate' || 
                    resource.type === 'Well' || 
                    resource.type === 'ResourceHolder') {
                    scale = 2.0;  // Larger scale for plates and wells
                }
                
                const x = resource.location.x * scale;
                const y = resource.location.y * scale;
                const width = resource.size_x * scale;
                const height = resource.size_y * scale;
                
                ctx.strokeStyle = '#000000';
                
                switch(resource.type) {
                    case 'STARLetDeck':
                        ctx.fillStyle = COLORS.DECK;
                        ctx.fillRect(x, y, width, height);
                        ctx.strokeRect(x, y, width, height);
                        break;
                        
                    case 'TipRack':
                        ctx.fillStyle = COLORS.TIP_RACK;
                        ctx.fillRect(x, y, width, height);
                        ctx.strokeRect(x, y, width, height);
                        break;
                        
                    case 'TipSpot':
                        drawTipSpot(
                            ctx, 
                            x, y, 
                            width, height, 
                            resource.state && resource.state.has_tip
                        );
                        break;
                        
                    case 'Plate':
                        ctx.fillStyle = COLORS.PLATE;
                        ctx.fillRect(x, y, width, height);
                        ctx.strokeRect(x, y, width, height);
                        break;
                        
                    case 'Well':
                        if (resource.state && resource.state.liquids) {
                            const radius = Math.min(width, height) * 0.7;  // Much larger pie charts
                            const centerX = x + width / 2;
                            const centerY = y + height / 2;
                            drawPieChart(
                                ctx, 
                                centerX, 
                                centerY, 
                                radius, 
                                resource.state.liquids,
                                resource.state.max_volume || 1000
                            );
                        } else {
                            // Draw empty well
                            ctx.fillStyle = COLORS.WELL_EMPTY;
                            const radius = Math.min(width, height) * 0.7;
                            ctx.beginPath();
                            ctx.arc(x + width/2, y + height/2, radius, 0, Math.PI * 2);
                            ctx.fill();
                            ctx.stroke();
                        }
                        break;
                        
                    case 'Trough':
                        // Draw trough outline first
                        ctx.strokeStyle = '#000000';
                        ctx.lineWidth = 2;
                        
                        // Draw trough background
                        ctx.fillStyle = COLORS.TROUGH;
                        ctx.fillRect(x, y, width, height);
                        
                        if (resource.state && resource.state.liquids) {
                            const volume = resource.state.liquids.reduce((sum, l) => sum + l[1], 0);
                            const maxVolume = resource.state.max_volume || 1000;
                            const ratio = Math.min(volume / maxVolume, 1.0);  // Clamp ratio to 1.0
                            
                            if (ratio > 0) {
                                // For troughs, use the first compound's color
                                const compound = resource.state.liquids[0][0];
                                ctx.fillStyle = COLORS.COMPOUNDS[compound] || '#999999';
                                
                                // Calculate liquid height and position
                                const liquidHeight = Math.floor(height * ratio);  // Use floor to prevent rounding errors
                                const padding = 4;  // Increased padding
                                
                                // Create clipping path for liquid
                                ctx.save();  // Save current context
                                ctx.beginPath();
                                ctx.rect(x + padding, y + padding, width - (padding * 2), height - (padding * 2));
                                ctx.clip();  // Clip to trough boundaries
                                
                                // Draw liquid level
                                ctx.fillRect(
                                    x + padding,
                                    y + height - liquidHeight - padding,
                                    width - (padding * 2),
                                    liquidHeight
                                );
                                
                                ctx.restore();  // Restore context to remove clipping
                            }
                        }
                        
                        // Draw trough outline last to ensure clean edges
                        ctx.strokeRect(x, y, width, height);
                        ctx.lineWidth = 1;
                        break;
                }
                
                // Draw children recursively with appropriate scaling
                if (resource.children) {
                    resource.children.forEach(child => {
                        // Preserve parent's scale for nested components
                        if (child.type === 'Well' || 
                            (resource.type === 'Plate' && child.type !== 'TipSpot')) {
                            child.parentScale = scale;
                        }
                        drawResource(child);
                    });
                }
            }
            
            drawResource(state);
            
            // Add frame to GIF
            encoder.addFrame(ctx);
        }

        // Read frames directory from command line
        const framesDir = process.argv[4];
        console.log('Reading frames from:', framesDir);

        // Read state files and render frames
        const stateFiles = fs.readdirSync(framesDir)
            .filter(f => f.endsWith('.json'))
            .sort();

        console.log('Found frame files:', stateFiles);

        stateFiles.forEach(file => {
            console.log('Processing frame:', file);
            const state = JSON.parse(fs.readFileSync(path.join(framesDir, file)));
            renderFrame(state);
            console.log('Added frame to GIF');
        });

        // Finish GIF
        encoder.finish();
        console.log('GIF generation complete');
        """
        
        with open(self.temp_dir / 'render.js', 'w') as f:
            f.write(node_script)

        # Create package.json
        package_json = {
            "dependencies": {
                "canvas": "^2.11.0",
                "gifencoder": "^2.0.1"
            }
        }
        with open(self.temp_dir / 'package.json', 'w') as f:
            json.dump(package_json, f)

        # Install dependencies
        subprocess.run(['npm', 'install'], cwd=self.temp_dir, check=True)

    async def _capture_frame(self, event_name: str):
        """Capture the current state as a frame."""
        frame_path = self.output_dir / f"frame_{self.frame_count:04d}_{event_name}.json"
        self.logger.debug(f"Capturing frame {self.frame_count} for event {event_name}")
        
        state = self._get_current_state()
        self.logger.debug(f"Got state for frame, saving to {frame_path}")
        
        with open(frame_path, "w") as f:
            json.dump(state, f, indent=2)
            
        self.frame_count += 1
        self.logger.debug(f"Frame {self.frame_count} saved")

    def _get_current_state(self) -> Dict[str, Any]:
        """Get the current state of all resources."""
        def serialize_resource(resource: Resource) -> Dict[str, Any]:
            location = resource.get_absolute_location()
            state = {
                "name": resource.name,
                "type": resource.__class__.__name__,
                "location": {
                    "x": location.x,
                    "y": location.y,
                    "z": location.z
                },
                "size_x": resource._size_x,
                "size_y": resource._size_y,
                "size_z": resource._size_z,
                "state": resource.serialize_state()
            }
            
            if hasattr(resource, "children"):
                state["children"] = [
                    serialize_resource(child) for child in resource.children
                ]
            
            return state
            
        return serialize_resource(self._root_resource)

    async def stop(self):
        """Stop the visualizer and create the GIF."""
        self.logger.info("Creating GIF from frames...")
        self.logger.info(f"Output directory: {self.output_dir}")
        self.logger.info(f"Frame count: {self.frame_count}")
        
        # List all frames
        frames = list(self.output_dir.glob('*.json'))
        self.logger.info(f"Found {len(frames)} frame files: {[f.name for f in frames]}")
        
        # Run Node.js script to create GIF
        cmd = [
            'node', 'render.js',
            str(self.gif_path),
            str(self.frame_delay),
            str(self.output_dir)
        ]
        self.logger.info(f"Running command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
                text=True
            )
            self.logger.info("Node.js output:")
            self.logger.info(result.stdout)
            if result.stderr:
                self.logger.error("Node.js errors:")
                self.logger.error(result.stderr)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to run Node.js script: {e}")
            self.logger.error("Node.js output:")
            self.logger.error(e.stdout)
            self.logger.error("Node.js errors:")
            self.logger.error(e.stderr)
            raise
        
        # Check if GIF was created
        if os.path.exists(self.gif_path):
            self.logger.info(f"GIF saved to {self.gif_path}")
        else:
            self.logger.error(f"GIF was not created at {self.gif_path}")
        
        await super().stop()
