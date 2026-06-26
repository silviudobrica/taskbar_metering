#!/usr/bin/env python3
"""
Generate a simple icon for Taskbar Metering
"""
import os
from PIL import Image, ImageDraw, ImageFont

# Create a 256x256 image with dark background
icon_size = 256
img = Image.new('RGBA', (icon_size, icon_size), color=(18, 18, 20, 255))
draw = ImageDraw.Draw(img)

# Draw a dark blue circle (represents tray)
circle_radius = 100
center_x = icon_size // 2
center_y = icon_size // 2
circle_color = (41, 121, 255)  # #2979FF
draw.ellipse(
    [center_x - circle_radius, center_y - circle_radius,
     center_x + circle_radius, center_y + circle_radius],
    fill=circle_color,
    outline=(100, 150, 255)
)

# Draw upward trending lines (CPU/metrics)
line_color = (255, 255, 255)
line_width = 4

# Three data points trending up
points = [
    (center_x - 40, center_y + 20),    # Low point
    (center_x, center_y - 10),          # Mid point
    (center_x + 40, center_y - 40),     # High point
]

# Draw lines connecting points
for i in range(len(points) - 1):
    draw.line([points[i], points[i+1]], fill=line_color, width=line_width)

# Draw dots at each point
dot_radius = 6
for point in points:
    draw.ellipse(
        [point[0] - dot_radius, point[1] - dot_radius,
         point[0] + dot_radius, point[1] + dot_radius],
        fill=line_color
    )

# Save as PNG
output_path = 'taskbar_metering_icon.png'
img.save(output_path, 'PNG')
print(f"✓ Icon created: {output_path}")

# Also save as ICO (for Windows)
try:
    ico_path = 'taskbar_metering.ico'
    img.save(ico_path, 'ICO')
    print(f"✓ ICO file created: {ico_path}")
except Exception as e:
    print(f"Note: ICO creation failed: {e}")
