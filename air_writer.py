import cv2
import pygame
import numpy as np
import math

import time

class AirWriter:
    def __init__(self):
        self.strokes = []  # List of {'points': [...], 'color': (R, G, B)}
        self.current_stroke = []
        self.drawing = False
        
        # Color palette
        self.colors = [
            (0, 220, 255),   # Neon Cyan
            (60, 255, 120),  # Green Neon
            (255, 60, 60),   # Red Hot
            (255, 230, 0),   # Yellow Neon
            (160, 60, 255)   # Purple
        ]
        self.color_idx = 0
        self.color = self.colors[self.color_idx]
        self.thickness = 4
        
        # UI Buttons for changing colors
        self.button_radius = 25
        self.button_spacing = 75
        self.button_y = 60
        self.buttons = []
        for i, c in enumerate(self.colors):
            x = 80 + i * self.button_spacing
            self.buttons.append({
                "x": x,
                "y": self.button_y,
                "color": c
            })
        self.last_button_click = 0
        
        # Eraser state
        self.eraser_pos = None
        self.eraser_radius = 60
        
        # Smart smoothing
        self.points_window = []
        self.window_size = 5
        
        # Commands
        self.last_clear_time = 0
        self.last_undo_time = 0
        self.last_color_time = 0
        
    def cycle_color(self):
        self.color_idx = (self.color_idx + 1) % len(self.colors)
        self.color = self.colors[self.color_idx]

    def process_hand(self, hand_state, now=0):
        if now == 0:
            now = time.time()
            
        raw_x = hand_state.index_tip.x
        raw_y = hand_state.index_tip.y
        
        # Check UI button collision
        for i, btn in enumerate(self.buttons):
            dist = math.hypot(raw_x - btn["x"], raw_y - btn["y"])
            if dist < self.button_radius + 20:  # slightly larger hit box
                if now - self.last_button_click > 0.3:
                    self.color_idx = i
                    self.color = self.colors[i]
                    self.last_button_click = now
                
                # If hovering over a button, don't draw
                self.drawing = False
                self.current_stroke = []
                self.points_window = []
                return
        
        features = hand_state.finger_open_states
        idx_open = features.get("index", False)
        mid_closed = not features.get("middle", True)
        rng_closed = not features.get("ring", True)
        pnk_closed = not features.get("pinky", True)
        
        # Less strict gesture constraints (thumb often read as open, pinky might twitch)
        is_writing_gesture = idx_open and mid_closed and rng_closed
        is_eraser = hand_state.is_open_palm
        
        raw_x = hand_state.index_tip.x
        raw_y = hand_state.index_tip.y
        
        if is_eraser:
            is_writing_gesture = False
            self.eraser_pos = (int(hand_state.middle_tip.x), int(hand_state.middle_tip.y))
            self.drawing = False
            self.current_stroke = []
            self.points_window = []
            
            # Erase points in strokes within radius by splitting them
            new_strokes = []
            for stroke_data in self.strokes:
                pts = stroke_data['points']
                new_pts = []
                for p in pts:
                    if math.hypot(p[0] - self.eraser_pos[0], p[1] - self.eraser_pos[1]) > self.eraser_radius:
                        new_pts.append(p)
                    else:
                        if len(new_pts) > 1:
                            new_strokes.append({'points': new_pts, 'color': stroke_data['color']})
                        new_pts = []
                if len(new_pts) > 1:
                    new_strokes.append({'points': new_pts, 'color': stroke_data['color']})
            self.strokes = new_strokes
            
        else:
            self.eraser_pos = None

        if is_writing_gesture:
            self.drawing = True
            
            # Smart smoothing: Moving average filter
            self.points_window.append((raw_x, raw_y))
            if len(self.points_window) > self.window_size:
                self.points_window.pop(0)
                
            smooth_x = sum(p[0] for p in self.points_window) / len(self.points_window)
            smooth_y = sum(p[1] for p in self.points_window) / len(self.points_window)
            
            self.current_stroke.append((int(smooth_x), int(smooth_y)))
        else:
            if self.drawing:
                # Finish stroke
                if len(self.current_stroke) > 1:
                    self.strokes.append({'points': list(self.current_stroke), 'color': self.color})
                self.current_stroke = []
                self.points_window = []
                self.drawing = False

    def clear_canvas(self):
        self.strokes = []
        self.current_stroke = []
        self.points_window = []
        self.drawing = False

    def undo_last_stroke(self):
        if self.strokes:
            self.strokes.pop()
        self.current_stroke = []
        self.points_window = []
        self.drawing = False

    def render_cv2(self, frame):
        # Draw all finished strokes
        for stroke_data in self.strokes:
            stroke = stroke_data['points']
            color = stroke_data['color']
            for i in range(1, len(stroke)):
                cv2.line(frame, stroke[i-1], stroke[i], color[::-1], self.thickness, cv2.LINE_AA)
        
        # Draw current stroke
        for i in range(1, len(self.current_stroke)):
            cv2.line(frame, self.current_stroke[i-1], self.current_stroke[i], self.color[::-1], self.thickness, cv2.LINE_AA)

        # Draw UI Buttons
        for i, btn in enumerate(self.buttons):
            # Base color
            cv2.circle(frame, (btn["x"], btn["y"]), self.button_radius, btn["color"][::-1], -1)
            
            # Highlight selected color
            if i == self.color_idx:
                cv2.circle(frame, (btn["x"], btn["y"]), self.button_radius + 6, (255, 255, 255), 2)
            else:
                cv2.circle(frame, (btn["x"], btn["y"]), self.button_radius, (255, 255, 255), 1)

        # Draw glowing particle and light trail if drawing
        if self.drawing and self.current_stroke:
            last_pt = self.current_stroke[-1]
            cv2.circle(frame, last_pt, 6, (255, 255, 255), -1)  # white core
            cv2.circle(frame, last_pt, 12, self.color[::-1], 2) # glow ring
            
        # Draw eraser
        if self.eraser_pos:
            # White transparent-looking circle for eraser
            overlay = frame.copy()
            cv2.circle(overlay, self.eraser_pos, self.eraser_radius, (200, 200, 200), -1)
            cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)
            cv2.circle(frame, self.eraser_pos, self.eraser_radius, (255, 255, 255), 2)

    def render_pygame(self, surface):
        pass # Optional to render on pygame, but using CV2 for anti-aliasing and glow over live feed is good.
