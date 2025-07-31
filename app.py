#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import copy
import cv2 as cv
import mediapipe as mp
import websockets
import asyncio
import json
from utils import CvFpsCalc

def get_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--width", help='cap width', type=int, default=960)
    parser.add_argument("--height", help='cap height', type=int, default=540)
    parser.add_argument("--ws_url", help='WebSocket URL', type=str, default='ws://asl.34.63.222.25.nip.io/api/asl/predict')

    parser.add_argument('--use_static_image_mode', action='store_true')
    # Sets the minimum confidence score required to detect a hand in the current frame.
    parser.add_argument("--min_detection_confidence",
                        help='min_detection_confidence',
                        type=float,
                        default=0.7)
    
    # Sets the minimum confidence score for tracking hands across frames after initial detection.
    parser.add_argument("--min_tracking_confidence",
                        help='min_tracking_confidence',
                        type=int,
                        default=0.5)

    args = parser.parse_args()
    return args

async def main():
    # Argument parsing
    args = get_args()

    cap_device = args.device
    cap_width = args.width
    cap_height = args.height
    ws_url = args.ws_url

    use_static_image_mode = args.use_static_image_mode
    min_detection_confidence = args.min_detection_confidence
    min_tracking_confidence = args.min_tracking_confidence

    use_brect = True

    # Camera preparation
    cap = cv.VideoCapture(cap_device)
    cap.set(cv.CAP_PROP_FRAME_WIDTH, cap_width)
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, cap_height)

    # Model load
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        static_image_mode=use_static_image_mode,
        max_num_hands=2, # detects the number of hands in the program
        min_detection_confidence=min_detection_confidence,
        min_tracking_confidence=min_tracking_confidence,
    )

    # FPS Measurement
    # initializes an object that measures the Frames Per Second (FPS) 
    # of your webcam/video processing loop, using a rolling average.
    cvFpsCalc = CvFpsCalc(buffer_len=10)

    async with websockets.connect(ws_url) as websocket:
        print(f"Connected to WebSocket server at {ws_url}")
        
        try:
            while True:
                fps = cvFpsCalc.get_fps()

                # Process Key (ESC: end)
                key = cv.waitKey(10)
                if key == 27:  # ESC
                    # Send close frame to server before breaking
                    await websocket.close(code=1000, reason="User requested exit")
                    break

                # Camera capture
                ret, image = cap.read()
                if not ret:
                    await websocket.close(code=1000, reason="Camera capture failed")
                    break
                    
                image = cv.flip(image, 1)  # Mirror display
                debug_image = copy.deepcopy(image)

                # Detection implementation
                image = cv.cvtColor(image, cv.COLOR_BGR2RGB)
                image.flags.writeable = False
                results = hands.process(image)
                image.flags.writeable = True

                if results.multi_hand_landmarks is not None:
                    for hand_landmarks, handedness in zip(results.multi_hand_landmarks,
                                                        results.multi_handedness):
                        # Bounding box calculation
                        brect = calc_bounding_rect(debug_image, hand_landmarks)
                        
                        # Landmark calculation
                        landmark_list = calc_landmark_list(debug_image, hand_landmarks)
                        
                        # Send landmark data to WebSocket server
                        try:
                            message = {
                                "data": landmark_list
                            }
                            await websocket.send(json.dumps(message))
                            
                            # Receive prediction from server
                            response = await websocket.recv()
                            prediction_data = json.loads(response)
                            
                            # Draw the results
                            debug_image = draw_bounding_rect(use_brect, debug_image, brect)
                            debug_image = draw_landmarks(debug_image, landmark_list)
                            debug_image = draw_info_text(
                                debug_image,
                                brect,
                                handedness,
                                prediction_data.get("prediction", ""),
                                ""  # No finger gesture text as we're not processing it locally
                            )
                        except websockets.exceptions.ConnectionClosed:
                            print("WebSocket connection was closed")
                            break
                        except Exception as e:
                            print(f"WebSocket error: {str(e)}")
                            await websocket.close(code=1000, reason=f"Error: {str(e)}")
                            break

                # Draw FPS
                debug_image = draw_info(debug_image, fps)

                # Screen reflection
                cv.imshow('Hand Gesture Recognition', debug_image)

        except websockets.exceptions.ConnectionClosed:
            print("WebSocket connection was closed")
        except Exception as e:
            print(f"Error in main loop: {str(e)}")
            try:
                await websocket.close(code=1000, reason=f"Error: {str(e)}")
            except:
                pass
        finally:
            # Release camera and destroy windows
            cap.release()
            cv.destroyAllWindows()

def calc_bounding_rect(image, landmarks):
    image_width, image_height = image.shape[1], image.shape[0]

    landmark_array = np.empty((0, 2), int)

    for _, landmark in enumerate(landmarks.landmark):
        landmark_x = min(int(landmark.x * image_width), image_width - 1)
        landmark_y = min(int(landmark.y * image_height), image_height - 1)

        landmark_point = [np.array((landmark_x, landmark_y))]
        landmark_array = np.append(landmark_array, landmark_point, axis=0)

    # x and y: top-left corner coordinates
    # width and height: how big the box is
    x, y, w, h = cv.boundingRect(landmark_array)
    
    # x + w: bottom-right corner coordinates
    # y + h: bottom-right corner coordinates
    return [x, y, x + w, y + h]

def calc_landmark_list(image, landmarks):
    image_width, image_height = image.shape[1], image.shape[0]

    landmark_point = []

    # Keypoint
    for _, landmark in enumerate(landmarks.landmark):
        landmark_x = min(int(landmark.x * image_width), image_width - 1)
        landmark_y = min(int(landmark.y * image_height), image_height - 1)
        landmark_point.append([landmark_x, landmark_y])

    return landmark_point

def draw_landmarks(image, landmark_point):
    if len(landmark_point) > 0:
        # Thumb
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[3]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[3]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[3]), tuple(landmark_point[4]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[3]), tuple(landmark_point[4]),
                (255, 255, 255), 2)

        # Index finger
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[6]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[6]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[6]), tuple(landmark_point[7]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[6]), tuple(landmark_point[7]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[7]), tuple(landmark_point[8]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[7]), tuple(landmark_point[8]),
                (255, 255, 255), 2)

        # Middle finger
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[10]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[10]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[10]), tuple(landmark_point[11]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[10]), tuple(landmark_point[11]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[11]), tuple(landmark_point[12]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[11]), tuple(landmark_point[12]),
                (255, 255, 255), 2)

        # Ring finger
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[14]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[14]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[14]), tuple(landmark_point[15]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[14]), tuple(landmark_point[15]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[15]), tuple(landmark_point[16]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[15]), tuple(landmark_point[16]),
                (255, 255, 255), 2)

        # Little finger
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[18]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[18]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[18]), tuple(landmark_point[19]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[18]), tuple(landmark_point[19]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[19]), tuple(landmark_point[20]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[19]), tuple(landmark_point[20]),
                (255, 255, 255), 2)

        # Palm
        cv.line(image, tuple(landmark_point[0]), tuple(landmark_point[1]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[0]), tuple(landmark_point[1]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[1]), tuple(landmark_point[2]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[1]), tuple(landmark_point[2]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[5]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[5]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[9]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[9]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[13]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[13]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[17]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[17]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[0]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[0]),
                (255, 255, 255), 2)

    # Key Points
    for index, landmark in enumerate(landmark_point):
        # landmark[0]: x, landmark[1]: y
        # draw a circle on the image
        # (landmark[0], landmark[1]): center coordinates
        # 8 if the landmark is a finger tip else 5: radius
        # (255, 255, 255): color
        # -1: thickness
        # 1: thickness
        # 2 circle: one for the outer circle, one for the inner circle
        cv.circle(image, (landmark[0], landmark[1]), 
                 8 if index in [4, 8, 12, 16, 20] else 5,
                 (255, 255, 255), -1)
        cv.circle(image, (landmark[0], landmark[1]), 
                 8 if index in [4, 8, 12, 16, 20] else 5,
                 (0, 0, 0), 1)

    return image

def draw_bounding_rect(use_brect, image, brect):
    if use_brect:
        # Outer rectangle
        # brect[0]: x, brect[1]: y, brect[2]: x + w, brect[3]: y + h
        # cv.rectangle: Draw a rectangle on the image
        # (brect[0], brect[1]): Top-left corner coordinates
        # (brect[2], brect[3]): Bottom-right corner coordinates
        # (0, 0, 0): Color of the rectangle (black)
        # 1: Thickness of the rectangle
        cv.rectangle(image, (brect[0], brect[1]), (brect[2], brect[3]),
                     (0, 0, 0), 1)

    return image

def draw_info_text(image, brect, handedness, hand_sign_text,
                   finger_gesture_text):
    # Draw a rectangle on the image
    # (brect[0], brect[1]): Top-left corner coordinates
    # (brect[2], brect[1] - 22): Bottom-right corner coordinates, -22 is the height of the rectangle
    # (0, 0, 0): Color of the rectangle (black)
    # -1: Thickness of the rectangle
    cv.rectangle(image, (brect[0], brect[1]), (brect[2], brect[1] - 22),
                 (0, 0, 0), -1)

    info_text = handedness.classification[0].label[0:] # info_text: the text to be displayed
    if hand_sign_text != "":
        info_text = info_text + ':' + hand_sign_text
    cv.putText(
        image, 
        info_text, # text to be displayed
        (brect[0] + 5, brect[1] - 4), # position
        cv.FONT_HERSHEY_SIMPLEX, 
        0.6,  # font size
        (255, 255, 255), # color
        1, # thickness
        cv.LINE_AA
    )

    return image

def draw_info(image, fps):
    cv.putText(image, "FPS:" + str(fps), (10, 30), cv.FONT_HERSHEY_SIMPLEX,
               1.0, (0, 0, 0), 4, cv.LINE_AA)
    cv.putText(image, "FPS:" + str(fps), (10, 30), cv.FONT_HERSHEY_SIMPLEX,
               1.0, (255, 255, 255), 2, cv.LINE_AA)
    return image

if __name__ == '__main__':
    import numpy as np
    asyncio.run(main())
