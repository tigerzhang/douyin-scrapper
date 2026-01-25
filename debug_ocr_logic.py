from PIL import Image, ImageOps, ImageFilter
import pytesseract
import os
import sys

def test_ocr_variants(image_path):
    if not os.path.exists(image_path):
        print(f"Image {image_path} not found.")
        return

    img = Image.open(image_path)
    # Focus on a small piece of the comment area for testing
    # Assuming comments are on the right side
    test_crop = img.crop((850, 150, 1400, 600))
    test_crop.save("debug_ocr_original.png")

    results = []

    # Variant 1: Grayscale only (Current)
    gray = test_crop.convert('L')
    results.append(("Grayscale", pytesseract.image_to_string(gray, lang='chi_sim+eng', config='--oem 3 --psm 6')))

    # Variant 2: Upscale 3x + Grayscale
    upscaled = gray.resize((gray.width * 3, gray.height * 3), Image.Resampling.LANCZOS)
    upscaled.save("debug_ocr_upscaled.png")
    results.append(("Upscale 3x", pytesseract.image_to_string(upscaled, lang='chi_sim+eng', config='--oem 3 --psm 6')))

    # Variant 3: Upscale 3x + Binary Thresholding
    threshold = 170
    binary = upscaled.point(lambda p: 255 if p > threshold else 0)
    binary.save("debug_ocr_binary.png")
    results.append(("Upscale + Binary", pytesseract.image_to_string(binary, lang='chi_sim+eng', config='--oem 3 --psm 6')))

    # Variant 4: Upscale 3x + AutoContrast + Binary
    contrasted = ImageOps.autocontrast(upscaled)
    binary_auto = contrasted.point(lambda p: 255 if p > 160 else 0)
    binary_auto.save("debug_ocr_binary_auto.png")
    results.append(("Upscale + AutoContrast + Binary", pytesseract.image_to_string(binary_auto, lang='chi_sim+eng', config='--oem 3 --psm 6')))

    print("\n--- OCR TEST RESULTS ---")
    for name, text in results:
        print(f"\n[{name}]:")
        print(text[:300] + "..." if len(text) > 300 else text)

if __name__ == "__main__":
    img_path = sys.argv[1] if len(sys.argv) > 1 else "debug_test_ocr.png"
    test_ocr_variants(img_path)
