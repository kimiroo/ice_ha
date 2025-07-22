import cv2
import base64

URL = "rtsp://10.5.38.100:555/live"

def capture_frame_and_encode_base64(rtsp_url):
    print(f"Attempting to open RTSP stream: {rtsp_url}")
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        print(f"Error: Could not open RTSP stream at {rtsp_url}.")
        return None

    # Read a single frame
    ret, frame = cap.read()

    # Release the VideoCapture object immediately
    cap.release()
    print("RTSP stream released.")

    if ret:
        print("Frame successfully captured. Encoding to Base64...")
        # Encode the OpenCV frame to JPEG format in memory
        # Quality can be adjusted (0-100), e.g., 90 for 90% quality
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
        ret_encode, buffer = cv2.imencode('.jpg', frame, encode_param)

        if not ret_encode:
            print("Error: Could not encode captured frame to JPEG buffer.")
            return None

        # Convert the buffer (numpy array of bytes) to a standard bytes object
        # then Base64 encode it and decode to utf-8 string
        base64_string = base64.b64encode(buffer.tobytes()).decode("utf-8")
        print("Image successfully Base64 encoded.")
        return base64_string
    else:
        print(f"Error: Could not read a frame from the stream {rtsp_url}.")
        print("This might happen if the stream is empty or disconnected immediately.")
        return None

print(capture_frame_and_encode_base64(URL))