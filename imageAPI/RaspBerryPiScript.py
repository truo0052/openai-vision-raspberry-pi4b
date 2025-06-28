import os
import sys
import subprocess
import logging
import datetime
import time
import base64
import requests
import select  # Added for polling input
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
import RPi.GPIO as GPIO

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Set up GPIO pins
BUTTON_CAPTURE = 20  # GPIO pin for capture button
BUTTON_UP = 26       # GPIO pin for scroll up button
BUTTON_DOWN = 21     # GPIO pin for scroll down button

# GPIO setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_CAPTURE, GPIO.IN, pull_up_down=GPIO.PUD_UP) # Using interior resistor
GPIO.setup(BUTTON_UP, GPIO.IN, pull_up_down=GPIO.PUD_UP) # Using interior resistor
GPIO.setup(BUTTON_DOWN, GPIO.IN, pull_up_down=GPIO.PUD_UP) # Using interior resistor

# Import LCD module
try:
    from lib import LCD_1inch5
    print("LCD imported")
except ImportError as e:
    print(f"LCD import error: {e}")
    sys.exit(1)

# Load environment variables from .env file
load_dotenv()

# OpenRouter API key
OPENAPI_KEY = os.getenv("OPENAPI_KEY")
if not OPENAPI_KEY:
    logger.error("OPENAPI_KEY not found in environment variables")
    sys.exit(1)

# Global variables
current_scroll_position = 0
image_description = ""
lcd_display = None

def sanitize_text(text):
    """Remove characters that can't be encoded in Latin-1"""
    return ''.join(c for c in text if ord(c) < 256)

def encode_image_to_base64(image_path):
    """Encode image to base64 for API requests"""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Error encoding image: {str(e)}")
        return None

def detect_image_orientation(image_path):
    """Detect image orientation using ChatGPT"""
    try:
        # Encode image to base64
        encoded_image = encode_image_to_base64(image_path)
        if not encoded_image:
            return 0  # Default to no rotation if encoding fails

        # Prepare the request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAPI_KEY}"
        }

        # Use ChatGPT for orientation detection
        data = {
            "model": "openai/gpt-4o-2024-08-06",
            "messages": [
                {
                    "role": "system",
                    "content": "You are an image orientation specialist. Your only task is to detect if content in an image needs rotation."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Look at this image and tell me ONLY what rotation angle is needed to make the content upright and properly oriented. Reply ONLY with one number: 0, 90, 180, or 270 degrees. Don't explain your answer, just provide the number."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded_image}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0
        }

        # Make the API request
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data
        )

        if response.status_code == 200:
            result = response.json()
            orientation_response = result['choices'][0]['message']['content']
            # Sanitize the response
            orientation_response = sanitize_text(orientation_response)

            # Try to extract just the number
            try:
                # Extract numeric part
                rotation_angle = int(''.join(filter(str.isdigit, orientation_response)))
                # Only accept valid rotation angles
                if rotation_angle not in [0, 90, 180, 270]:
                    return 0
                return rotation_angle
            except (ValueError, TypeError):
                return 0
        else:
            logger.error(f"Orientation detection API error: {response.status_code} - {response.text}")
            return 0

    except Exception as e:
        logger.error(f"Error detecting orientation: {str(e)}")
        return 0  # Default to no rotation

def capture_and_rotate_image():
    """Capture an image and auto-rotate it using ChatGPT for orientation detection"""
    # Create the output directory if it doesn't exist
    image_output_dir = "/home/username/imageAPI/Pictures"
    os.makedirs(image_output_dir, exist_ok=True)

    # Fixed filenames
    raw_image_path = os.path.join(image_output_dir, "capture.jpg")
    rotated_image_path = os.path.join(image_output_dir, "capture_rotated.jpg")

    try:
        # Step 1: Capture the raw image
        capture_cmd = [
            "libcamera-still",
            "-o", raw_image_path,
            "--ev", "0.5",
            "--width", "1920",
            "--height", "1080"
        ]
        subprocess.run(capture_cmd, check=True)
        logger.info(f"Image captured and saved to {raw_image_path}")

        # Detect orientation using GPT-4V
        display_text_on_lcd("Detecting orientation...")
        detected_rotation = detect_image_orientation(raw_image_path)
        logger.info(f"Detected rotation angle: {detected_rotation}")

        # Rotate the image if needed
        if detected_rotation != 0:
            # Open the image
            with Image.open(raw_image_path) as captured_img:
                # Rotate it
                rotated_img = captured_img.rotate(-detected_rotation, expand=True)  # Negative because PIL rotates counter-clockwise
                # Save the rotated image
                rotated_img.save(rotated_image_path)
                logger.info(f"Image rotated by {detected_rotation} degrees and saved to {rotated_image_path}")
                return rotated_image_path

        # No rotation needed
        return raw_image_path

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to capture image: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None

def analyze_image_content(image_path):
    """Analyze and extract content from image using google/gemini-2.5-pro via OpenRouter"""
    try:
        logger.info(f"Analyzing image content: {image_path}")

        # Encode image to base64
        encoded_image = encode_image_to_base64(image_path)
        if not encoded_image:
            return "Error encoding image"

        # Prepare the request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAPI_KEY}"
        }

        # Use Gemini for content analysis
        data = {
            "model": "google/gemini-2.5-pro-preview-05-06",
            "messages": [
                {
                    "role": "system",
                    "content": "You are an image analysis specialist. Your task is to accurately identify and describe the contents of images."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analyze this image and identify what items, objects, or content you can see. Do not include the background. Just analyse the product or object in the image."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded_image}"
                            }
                        }
                    ]
                }
            ]
        }

        # Make the API request
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data
        )

        # Check for successful response
        if response.status_code == 200:
            result = response.json()
            analyzed_content = result['choices'][0]['message']['content']
            # Sanitize the extracted content
            analyzed_content = sanitize_text(analyzed_content)
            logger.info("Successfully analyzed image content")
            return analyzed_content
        else:
            logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
            return f"Error: {response.status_code} - {response.text}"

    except Exception as e:
        logger.error(f"Error in image analysis: {str(e)}")
        logger.error(f"Error details: {sys.exc_info()}")
        return f"Error analyzing image: {str(e)}"

def generate_description_with_gemini(image_content):
    """Generate detailed description using Gemini"""
    try:
        logger.info("Generating detailed description...")

        # Prepare the request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAPI_KEY}"
        }

        # Use Gemini for generating detailed description
        data = {
            "model": "google/gemini-2.5-pro",
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert at describing images and identifying objects. Provide clear, detailed descriptions of what items or objects are present in images."
                },
                {
                    "role": "user",
                    "content": f"""
Based on this image analysis, provide a clear and short answer of what items or objects are in this image:

--- Image Content Analysis ---
{image_content}
--- End Analysis ---

Please describe what you can identify in this image, including:
- Main objects or items visible
- Do not include the background
"""
                }
            ],
            "temperature": 0.3
        }

        # Make the API request
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data
        )

        # Check for successful response
        if response.status_code == 200:
            result = response.json()
            detailed_description = result['choices'][0]['message']['content']
            # Sanitize the description
            detailed_description = sanitize_text(detailed_description)
            logger.info("Successfully generated description")
            return detailed_description
        else:
            logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
            return f"Error: {response.status_code} - {response.text}"

    except Exception as e:
        logger.error(f"Error generating description: {str(e)}")
        logger.error(f"Error details: {sys.exc_info()}")
        return f"Error generating description: {str(e)}"

def display_text_on_lcd(text, scroll_position=0, content_type="normal"):
    """Display text on LCD with 270-degree rotation and better top padding"""
    global lcd_display

    # Sanitize text before display
    text = sanitize_text(text)

    if lcd_display is None:
        logger.error("Display not initialized")
        return 0

    # Clear the display
    lcd_display.clear()

    # Create image with original dimensions first
    display_width = lcd_display.width
    display_height = lcd_display.height

    lcd_image = Image.new('RGB', (display_width, display_height), (0, 0, 0))
    draw = ImageDraw.Draw(lcd_image)

    # Font setup
    font_size = 14
    try:
        display_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size)
    except IOError:
        try:
            display_font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf", font_size)
        except IOError:
            display_font = ImageFont.load_default()

    # Padding settings
    horizontal_padding = 10
    top_padding = 20
    bottom_padding = 8

    available_text_width = display_width - (horizontal_padding * 2)
    line_height = font_size + 2
    available_text_height = display_height - top_padding - bottom_padding
    max_visible_lines = available_text_height // line_height

    # Word wrapping
    wrapped_text_lines = []
    for paragraph in text.split('\n'):
        if not paragraph.strip():
            wrapped_text_lines.append("")
            continue

        words = paragraph.split()
        if not words:
            wrapped_text_lines.append("")
            continue

        current_line = ""
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            bbox = draw.textbbox((0, 0), test_line, font=display_font)
            text_width = bbox[2] - bbox[0]

            if text_width <= available_text_width:
                current_line = test_line
            else:
                if current_line:
                    wrapped_text_lines.append(current_line)
                    current_line = word
                else:
                    if word:
                        for i, char in enumerate(word):
                            test_word = word[:i+1]
                            bbox = draw.textbbox((0, 0), test_word, font=display_font)
                            if bbox[2] - bbox[0] > available_text_width and i > 0:
                                wrapped_text_lines.append(word[:i])
                                current_line = word[i:]
                                break
                        else:
                            current_line = word

        if current_line:
            wrapped_text_lines.append(current_line)

    # Apply scroll position
    start_line = max(0, min(scroll_position, max(0, len(wrapped_text_lines) - max_visible_lines)))
    visible_text_lines = wrapped_text_lines[start_line:start_line + max_visible_lines]

    # Draw the text
    y_position = top_padding
    for i, line in enumerate(visible_text_lines):
        if y_position + line_height <= display_height - bottom_padding:
            draw.text((horizontal_padding, y_position), line, font=display_font, fill=(255, 255, 255))
            y_position += line_height
        else:
            break

    # Rotate the image by 270 degrees
    rotated_lcd_image = lcd_image.rotate(90, expand=True)

    # If the rotated image doesn't match display dimensions, resize it
    if rotated_lcd_image.size != (lcd_display.width, lcd_display.height):
        rotated_lcd_image = rotated_lcd_image.resize((lcd_display.width, lcd_display.height))

    # Update the display with rotated image
    lcd_display.ShowImage(rotated_lcd_image)

    return len(wrapped_text_lines)

def capture_and_describe_image():
    """Capture image and generate description using two-step approach"""
    global image_description, current_scroll_position

    # Reset scroll position
    current_scroll_position = 0

    # Step 1: Capture image with auto-rotation
    display_text_on_lcd("Capturing image...")
    captured_image_path = capture_and_rotate_image()
    if not captured_image_path:
        display_text_on_lcd("Failed to capture image. Please try again.")
        return

    # Step 2: Analyze image content
    display_text_on_lcd("Analyzing image content...")
    analyzed_content = analyze_image_content(captured_image_path)

    # Print analyzed content for debugging
    print("\nAnalyzed Image Content:")
    print(analyzed_content)

    # Step 3: Generate detailed description with Gemini
    display_text_on_lcd("Generating description...")
    image_description = generate_description_with_gemini(analyzed_content)

    # Print description for debugging
    print("\nGenerated Description:")
    print(image_description)

    # Step 4: Display the description
    display_text_on_lcd(image_description, current_scroll_position)

def main():
    global lcd_display, current_scroll_position, image_description

    try:
        # Initialize the display
        lcd_display = LCD_1inch5.LCD_1inch5()
        lcd_display.Init()
        lcd_display.clear()

        display_text_on_lcd("Image Analyzer Ready\nPress CAPTURE button to take a photo")

        while True:
            # Button handling with debouncing
            if not GPIO.input(BUTTON_CAPTURE):
                print("Capture button pressed")
                display_text_on_lcd("Capturing image...")
                capture_and_describe_image()
                time.sleep(0.5)  # Debounce delay

            if not GPIO.input(BUTTON_UP) and image_description:
                print("Up button pressed")
                if current_scroll_position > 0:
                    current_scroll_position -= 1
                    total_lines = display_text_on_lcd(image_description, current_scroll_position)
                    print(f"Scrolled up to position {current_scroll_position}")
                time.sleep(0.3)

            if not GPIO.input(BUTTON_DOWN) and image_description:
                print("Down button pressed")
                total_lines = display_text_on_lcd(image_description, current_scroll_position + 1)

                # Calculate max scroll position
                line_height = 12  # font_size + spacing
                max_visible_lines = (lcd_display.height - 4) // line_height
                max_scroll_position = max(0, total_lines - max_visible_lines)

                if current_scroll_position < max_scroll_position:
                    current_scroll_position += 1
                    display_text_on_lcd(image_description, current_scroll_position)
                    print(f"Scrolled down to position {current_scroll_position}")

                time.sleep(0.3)

        # Clear the display before exiting
        lcd_display.clear()
        logger.info("Exiting")

    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
    finally:
        try:
            GPIO.cleanup()
            lcd_display.module_exit()
        except:
            print("Shutdown failure")


if __name__ == "__main__":
    main()