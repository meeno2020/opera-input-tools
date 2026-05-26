"""
OCR Engine - cross-platform multi-display screenshot, OCR, coordinate conversion.
Uses mss for capture (macOS + Windows), pytesseract for OCR.
"""
import sys
from PIL import Image, ImageEnhance, ImageOps

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import pytesseract
    # On Windows, set tesseract path if installed via default installer
    if sys.platform == 'win32':
        import os
        _win_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(_win_path):
            pytesseract.pytesseract.tesseract_cmd = _win_path
except ImportError:
    pass


def get_all_displays() -> list[dict]:
    """Return all active displays. Index is 1-based (matches mss monitor list)."""
    if not _MSS:
        return [{'index': 1, 'logical_x': 0, 'logical_y': 0,
                 'logical_w': 1920, 'logical_h': 1080}]
    with mss.MSS() as sct:
        result = []
        for i, mon in enumerate(sct.monitors[1:], 1):   # monitors[0] = all combined
            result.append({
                'index':     i,
                'logical_x': mon['left'],
                'logical_y': mon['top'],
                'logical_w': mon['width'],
                'logical_h': mon['height'],
            })
        return result


def capture_display(display_index: int) -> Image.Image:
    """Capture a specific display (1-based index). Returns PIL Image (RGB)."""
    with mss.MSS() as sct:
        mon = sct.monitors[display_index]
        raw = sct.grab(mon)
        return Image.frombytes('RGB', raw.size, raw.bgra, 'raw', 'BGRX')


def screenshot_to_global(px: float, py: float, display: dict) -> tuple[int, int]:
    """
    Convert screenshot pixel coordinates to global logical coordinates for pyautogui.
    On Retina/HiDPI displays, mss returns physical pixels but pyautogui uses logical.
    """
    scale_x = display['_img_w'] / display['logical_w']
    scale_y = display['_img_h'] / display['logical_h']
    return (
        int(display['logical_x'] + px / scale_x),
        int(display['logical_y'] + py / scale_y),
    )


def ocr_words(pil_img: Image.Image, invert: bool = False,
              region: tuple[int, int, int, int] | None = None) -> list[dict]:
    """
    Run OCR on an image and return word list.
    region=(x, y, w, h) in image pixels — crops before OCR for higher accuracy;
    returned coordinates are offset back to full-image space.
    Set invert=True for dark-background dropdowns.
    """
    img = pil_img.convert('RGB')
    offset_x, offset_y = 0, 0
    if region:
        rx, ry, rw, rh = region
        img = img.crop((rx, ry, rx + rw, ry + rh))
        offset_x, offset_y = rx, ry
    if invert:
        img = ImageOps.invert(img)
    enhanced = ImageEnhance.Contrast(img).enhance(2.0)
    data = pytesseract.image_to_data(
        enhanced,
        output_type=pytesseract.Output.DICT,
        config='--psm 11 --oem 3',
    )
    return [
        {
            'text': data['text'][i].strip(),
            'x':    data['left'][i] + offset_x,
            'y':    data['top'][i] + offset_y,
            'w':    data['width'][i],
            'h':    data['height'][i],
            'conf': data['conf'][i],
        }
        for i in range(len(data['text']))
        if data['text'][i].strip() and data['conf'][i] > 20
    ]


def find_label_above(words: list[dict], cx: int, cy: int,
                     search_px: int = 150) -> dict | None:
    """Find the nearest label word directly above a click point."""
    candidates = [
        w for w in words
        if w['y'] < cy
        and w['y'] > cy - search_px
        and w['x'] < cx + 100
        and w['x'] + w['w'] > cx - 100
    ]
    return max(candidates, key=lambda w: w['y']) if candidates else None


def find_label_left(words: list[dict], cx: int, cy: int,
                    search_px: int = 300) -> dict | None:
    """Find the nearest label word to the left of a click point (same row)."""
    candidates = [
        w for w in words
        if w['x'] + w['w'] < cx
        and w['x'] + w['w'] > cx - search_px
        and abs((w['y'] + w['h'] // 2) - cy) < 30
    ]
    return max(candidates, key=lambda w: w['x'] + w['w']) if candidates else None
