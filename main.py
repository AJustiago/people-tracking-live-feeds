import tkinter as tk
from tkinter import messagebox
import cv2
from PIL import Image, ImageTk
import threading
import queue
from datetime import datetime
import pytz
from transformers import YolosImageProcessor, YolosForObjectDetection
import torch
import numpy as np
from mongo_utils import MongoDBHandler

class PolygonApp:
    def __init__(self, root):
        self.root = root
        self.root.title("People Tracking CCTV")

        try:
            self.mongo_handler = MongoDBHandler()
        except ConnectionError as e:
            messagebox.showerror("Error", str(e))
            self.root.destroy()
            return

        self.frame_queue = queue.Queue()

        self.main_frame = tk.Frame(root)
        self.main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        self.canvas = tk.Canvas(self.main_frame, width=640, height=480, highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, padx=5, pady=5)

        self.log_frame = tk.Frame(self.main_frame)
        self.log_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5)
        self.log_label = tk.Label(self.log_frame, text="Action Log", font=("Arial", 10, "bold"))
        self.log_label.pack()
        self.log_text = tk.Text(self.log_frame, height=20, width=40, state='disabled')
        self.log_text.pack(fill=tk.Y)
        self.log_scrollbar = tk.Scrollbar(self.log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text['yscrollcommand'] = self.log_scrollbar.set

        self.selected = None
        self.startxy = None
        self.polygons = [] 
        self.creating_polygon = False
        self.temp_points = []  
        self.temp_polygon_id = None
        self.selected_vertex = None
        self.video_running = True
        self.current_photo = None
        self.video_image_id = None
        self.person_tracker = {}  
        self.person_counter = 0 
        self.distance_threshold = 50 
        self.max_missed_frames = 30
        self.canvas_width = 640
        self.canvas_height = 480

        button_frame = tk.Frame(root)
        button_frame.pack(side=tk.BOTTOM)

        tk.Button(button_frame, text="Add Polygon", command=self.start_polygon_creation).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Clear All", command=self.clear_all).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Help", command=self.show_help).pack(side=tk.LEFT, padx=5)

        self.coord_text = tk.Text(root, height=4, width=50)
        self.coord_text.pack(side=tk.BOTTOM)
        self.coord_text.insert(tk.END, "Left-click to add points for a new polygon. Right-click to finish.\n"
                                      "Left-click and drag to move a polygon or vertex. Right-click to delete a polygon.\n")

        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right_click)

        self.hls_url = "https://cctvjss.jogjakota.go.id/margo-utomo/Selatan-Olive.stream/chunklist_w518845677.m3u8"
        self.cap = cv2.VideoCapture(self.hls_url)

        self.model = YolosForObjectDetection.from_pretrained('hustvl/yolos-tiny')
        self.image_processor = YolosImageProcessor.from_pretrained("hustvl/yolos-tiny")

        self.root.after(1000, self.load_polygons_from_db)

        self.video_thread = threading.Thread(target=self.update_video, daemon=True)
        self.video_thread.start()

        self.process_queue()

        self.show_help()

    def log_action(self, message):
        """Log an action with a timestamp to the log text widget."""
        wib = pytz.timezone('Asia/Jakarta')
        timestamp = datetime.now(wib).strftime('%Y-%m-%d %I:%M:%S %p WIB')
        self.log_text.configure(state='normal')
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.configure(state='disabled')
        self.log_text.see(tk.END)

    def show_help(self):
        """Display a help dialog with instructions for using the application."""
        help_text = (
            "People Tracking CCTV Instructions:\n\n"
            "1. Live Video: The canvas displays a live CCTV feed from Margo Utomo, Yogyakarta, with polygons drawn on top.\n"
            "2. Human Detection: Humans are detected using YOLO and tracked within polygons. Logs indicate the polygon index (0-based) when a person enters/leaves.\n"
            "3. Add Polygon: Click 'Add Polygon' and left-click to add points. Right-click to finish creating the polygon.\n"
            "4. Move Polygon: Left-click and drag inside a polygon to move it. The outline turns red while dragging.\n"
            "5. Resize Polygon: Left-click and drag a vertex (blue dot) to resize the polygon.\n"
            "6. Delete Polygon: Right-click on a polygon to mark it as deleted (with confirmation). Sets isDeleted to True in MongoDB.\n"
            "7. Clear All: Click 'Clear All' to mark all polygons as deleted (isDeleted: True) in MongoDB and clear the canvas (with confirmation).\n"
            "8. Coordinates: Selected or moved polygon coordinates are shown below.\n"
            "9. Action Log: Actions (add, load, and human enter/leave events with polygon index) are logged on the right and saved to MongoDB (people_tracking_logs.event_logs).\n"
            "10. Database: Polygons are saved to MongoDB (cctv_tracking.polygons) with an isDeleted flag. Enter/leave events are saved to people_tracking_logs.event_logs.\n"
        )
        messagebox.showinfo("Help", help_text)

    def load_polygons_from_db(self):
        """Load non-deleted polygons from MongoDB and draw them on the canvas."""
        self.polygons = []
        self.canvas.delete('polygon', 'vertex')  
        if hasattr(self, 'current_photo') and self.current_photo and not self.video_image_id:
            self.video_image_id = self.canvas.create_image(0, 0, image=self.current_photo, anchor='nw', tags='video')
        for poly in self.mongo_handler.load_polygons():
            points = poly.get('points', [])
            if not isinstance(points, list) or len(points) < 6 or len(points) % 2 != 0:
                self.log_action(f"Skipped invalid Polygon-{poly['index']} from database (invalid points: {points})")
                continue
            try:
                points = [float(p) for p in points]
                points = [max(0, min(self.canvas_width, p)) if i % 2 == 0 else max(0, min(self.canvas_height, p)) for i, p in enumerate(points)]
            except (ValueError, TypeError):
                self.log_action(f"Skipped Polygon-{poly['index']} from database (non-numeric points: {points})")
                continue
            polygon_id = self.canvas.create_polygon(points, fill='', outline='blue', width=3, tags='polygon')
            vertex_ids = []
            for i in range(0, len(points), 2):
                x, y = points[i], points[i+1]
                vertex_id = self.canvas.create_oval(x-5, y-5, x+5, y+5, fill='blue', tags='vertex')
                vertex_ids.append(vertex_id)
            self.polygons.append((polygon_id, points, vertex_ids))
            self.log_action(f"Loaded Polygon-{poly['index']} from database with points {points}")
           
            self.canvas.tag_raise(polygon_id)
            for vertex_id in vertex_ids:
                self.canvas.tag_raise(vertex_id)
        if not self.polygons:
            self.log_action("No active polygons found in database")
        if self.video_image_id:
            self.canvas.tag_lower(self.video_image_id)
        self.canvas.update()

    def is_point_in_polygon(self, point, polygon_id, points):
        """Check if a point is inside a polygon using ray-casting algorithm."""
        x, y = point
        n = len(points) // 2
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = points[2*i], points[2*i+1]
            xj, yj = points[2*j], points[2*j+1]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-10) + xi):
                inside = not inside
            j = i
        return inside

    def process_queue(self):
        """Process items from the frame queue in the main thread."""
        try:
            while True:
                item = self.frame_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "log":
                    self.log_action(item[1])
                else:
                    frame, person_tracker = item
                    self.latest_frame = frame
                    self.person_tracker = person_tracker
                    self.update_video_frame()
        except queue.Empty:
            pass
        if self.video_running:
            self.root.after(33, self.process_queue)

    def update_video_frame(self):
        """Update the canvas with the latest video frame."""
        if hasattr(self, 'latest_frame'):
            self.current_photo = ImageTk.PhotoImage(self.latest_frame)
            if self.video_image_id is None:
                self.video_image_id = self.canvas.create_image(0, 0, image=self.current_photo, anchor='nw', tags='video')
            else:
                self.canvas.itemconfig(self.video_image_id, image=self.current_photo)
            self.canvas.image = self.current_photo
            # Ensure video is at the bottom and polygons/vertices are on top
            self.canvas.tag_lower('video')
            for polygon_id, _, vertex_ids in self.polygons:
                self.canvas.tag_raise(polygon_id)
                for vertex_id in vertex_ids:
                    self.canvas.tag_raise(vertex_id)

    def update_video(self):
        """Process video frames and person tracking in a separate thread."""
        while self.video_running:
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.resize(frame, (640, 480))
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)

                inputs = self.image_processor(images=image, return_tensors="pt")
                outputs = self.model(**inputs)
                target_sizes = torch.tensor([image.size[::-1]])
                results = self.image_processor.post_process_object_detection(
                    outputs, threshold=0.8, target_sizes=target_sizes)[0]

                current_persons = []
                for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
                    if score > 0.85 and self.model.config.id2label[label.item()] in ('person', 'human'):
                        box = [round(i, 2) for i in box.tolist()]
                        x1, y1, x2, y2 = map(int, box)
                        center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
                        current_persons.append((center_x, center_y))

                new_tracker = {}
                used_previous_ids = set()
                for current_center in current_persons:
                    min_distance = float('inf')
                    best_id = None
                    for person_id, (prev_x, prev_y, polygon_index, missed_frames) in self.person_tracker.items():
                        if person_id in used_previous_ids:
                            continue
                        distance = np.sqrt((current_center[0] - prev_x) ** 2 + (current_center[1] - prev_y) ** 2)
                        if distance < min_distance and distance < self.distance_threshold:
                            min_distance = distance
                            best_id = person_id
                    if best_id is not None:
                        new_tracker[best_id] = (current_center[0], current_center[1],
                                               self.person_tracker[best_id][2], 0)
                        used_previous_ids.add(best_id)
                    else:
                        new_tracker[self.person_counter] = (current_center[0], current_center[1], None, 0)
                        self.person_counter += 1

                for person_id, (center_x, center_y, polygon_index, missed_frames) in list(self.person_tracker.items()):
                    if person_id not in used_previous_ids:
                        missed_frames += 1
                        if missed_frames >= self.max_missed_frames and polygon_index is not None:
                            self.frame_queue.put(("log", f"Person-{person_id} left Polygon-{polygon_index}"))
                            self.mongo_handler.save_event_log(person_id, polygon_index, "leave")
                            new_tracker[person_id] = (center_x, center_y, None, missed_frames)
                        elif missed_frames < self.max_missed_frames:
                            new_tracker[person_id] = (center_x, center_y, polygon_index, missed_frames)

                for person_id, (center_x, center_y, prev_polygon_index, missed_frames) in new_tracker.items():
                    if missed_frames >= self.max_missed_frames:
                        continue
                    inside_polygon_index = None
                    for idx, (polygon_id, points, _) in enumerate(self.polygons):
                        if self.is_point_in_polygon((center_x, center_y), polygon_id, points):
                            inside_polygon_index = idx
                            break
                    if prev_polygon_index is None and inside_polygon_index is not None:
                        self.frame_queue.put(("log", f"Person-{person_id} entered Polygon-{inside_polygon_index}"))
                        self.mongo_handler.save_event_log(person_id, inside_polygon_index, "enter")
                        new_tracker[person_id] = (center_x, center_y, inside_polygon_index, 0)
                    elif prev_polygon_index is not None and inside_polygon_index is None and missed_frames == 0:
                        self.frame_queue.put(("log", f"Person-{person_id} left Polygon-{prev_polygon_index}"))
                        self.mongo_handler.save_event_log(person_id, prev_polygon_index, "leave")
                        new_tracker[person_id] = (center_x, center_y, None, 0)
                    elif prev_polygon_index != inside_polygon_index and inside_polygon_index is not None:
                        self.frame_queue.put(("log", f"Person-{person_id} left Polygon-{prev_polygon_index}"))
                        self.mongo_handler.save_event_log(person_id, prev_polygon_index, "leave")
                        self.frame_queue.put(("log", f"Person-{person_id} entered Polygon-{inside_polygon_index}"))
                        self.mongo_handler.save_event_log(person_id, inside_polygon_index, "enter")
                        new_tracker[person_id] = (center_x, center_y, inside_polygon_index, 0)

                self.frame_queue.put((image, new_tracker))
            else:
                self.cap = cv2.VideoCapture(self.hls_url)

    def start_polygon_creation(self):
        """Start creating a new polygon."""
        if self.creating_polygon:
            self.finish_polygon_creation()
        self.creating_polygon = True
        self.temp_points = []
        self.temp_polygon_id = None
        self.coord_text.delete(1.0, tk.END)
        self.coord_text.insert(tk.END, "Left-click to add points. Right-click to finish.\n")

    def finish_polygon_creation(self):
        """Finish creating a polygon and save it to the database."""
        if len(self.temp_points) >= 6:  
            if not self.temp_points:
                center_x, center_y = 320, 240
                size = 50
                self.temp_points = [
                    center_x - size, center_y - size,
                    center_x + size, center_y - size,
                    center_x + size, center_y + size,
                    center_x - size, center_y + size
                ]

            self.temp_points = [max(0, min(self.canvas_width, p)) if i % 2 == 0 else max(0, min(self.canvas_height, p)) for i, p in enumerate(self.temp_points)]
            polygon_id = self.canvas.create_polygon(self.temp_points, fill='', outline='blue', width=3, tags='polygon')
            vertex_ids = []
            for i in range(0, len(self.temp_points), 2):
                x, y = self.temp_points[i], self.temp_points[i+1]
                vertex_id = self.canvas.create_oval(x-5, y-5, x+5, y+5, fill='blue', tags='vertex')
                vertex_ids.append(vertex_id)
            index = len(self.polygons)
            self.polygons.append((polygon_id, self.temp_points[:], vertex_ids))
            if self.mongo_handler.save_polygon(index, self.temp_points[:]):
                self.log_action(f"Added Polygon-{index} with {len(self.temp_points)//2} vertices")
            self.update_coordinates(polygon_id)
            # Raise new polygon and vertices above video
            self.canvas.tag_raise(polygon_id)
            for vertex_id in vertex_ids:
                self.canvas.tag_raise(vertex_id)
            if self.video_image_id:
                self.canvas.tag_lower(self.video_image_id)
            self.canvas.update()
        if self.temp_polygon_id:
            self.canvas.delete(self.temp_polygon_id)
        self.creating_polygon = False
        self.temp_points = []
        self.temp_polygon_id = None

    def on_click(self, event):
        """Handle left-click events on the canvas."""
        if self.creating_polygon:
            self.temp_points.extend([event.x, event.y])
            if len(self.temp_points) >= 6:
                if self.temp_polygon_id:
                    self.canvas.delete(self.temp_polygon_id)
                self.temp_polygon_id = self.canvas.create_polygon(self.temp_points, fill='', outline='blue', width=3, tags='polygon')
            return

        items = self.canvas.find_overlapping(event.x-5, event.y-5, event.x+5, event.y+5)
        for item in items:
            for polygon_id, points, vertex_ids in self.polygons:
                if item in vertex_ids:
                    self.selected = polygon_id
                    self.selected_vertex = vertex_ids.index(item)
                    self.startxy = (event.x, event.y)
                    self.canvas.itemconfig(polygon_id, width=4, outline='red')
                    self.update_coordinates(polygon_id)
                    return

        items = self.canvas.find_overlapping(event.x-10, event.y-10, event.x+10, event.y+10)
        for item in items:
            for polygon_id, _, _ in self.polygons:
                if item == polygon_id:
                    self.selected = polygon_id
                    self.selected_vertex = None
                    self.startxy = (event.x, event.y)
                    self.canvas.itemconfig(polygon_id, width=4, outline='red')
                    self.update_coordinates(polygon_id)
                    return

        self.selected = None
        self.selected_vertex = None
        self.coord_text.delete(1.0, tk.END)
        self.coord_text.insert(tk.END, "No polygon selected.\n")
        for polygon_id, _, _ in self.polygons:
            self.canvas.itemconfig(polygon_id, width=3, outline='blue')

    def on_drag(self, event):
        """Handle dragging of polygons or vertices."""
        if not self.selected or not self.startxy:
            return
        dx, dy = event.x - self.startxy[0], event.y - self.startxy[1]
        for idx, (polygon_id, points, vertex_ids) in enumerate(self.polygons):
            if polygon_id == self.selected:
                if self.selected_vertex is not None:
                    # Update single vertex
                    new_x = points[2*self.selected_vertex] + dx
                    new_y = points[2*self.selected_vertex + 1] + dy
                    # Clamp to canvas bounds
                    new_x = max(0, min(self.canvas_width, new_x))
                    new_y = max(0, min(self.canvas_height, new_y))
                    points[2*self.selected_vertex] = new_x
                    points[2*self.selected_vertex + 1] = new_y
                    self.canvas.coords(polygon_id, points)
                    vertex_id = vertex_ids[self.selected_vertex]
                    self.canvas.coords(vertex_id, new_x-5, new_y-5, new_x+5, new_y+5)
                else:
                    # Move entire polygon
                    for i in range(0, len(points), 2):
                        new_x = points[i] + dx
                        new_y = points[i+1] + dy
                        # Clamp to canvas bounds
                        new_x = max(0, min(self.canvas_width, new_x))
                        new_y = max(0, min(self.canvas_height, new_y))
                        points[i] = new_x
                        points[i+1] = new_y
                        vertex_id = vertex_ids[i//2]
                        self.canvas.coords(vertex_id, new_x-5, new_y-5, new_x+5, new_y+5)
                    self.canvas.coords(polygon_id, points)
                # Save to MongoDB
                self.mongo_handler.save_polygon(idx, points[:])
                self.update_coordinates(polygon_id)
                # Ensure polygon and vertices stay above video
                self.canvas.tag_raise(polygon_id)
                for vertex_id in vertex_ids:
                    self.canvas.tag_raise(vertex_id)
                if self.video_image_id:
                    self.canvas.tag_lower(self.video_image_id)
                self.canvas.update()
                break
        self.startxy = (event.x, event.y)

    def on_release(self, event):
        """Handle release of mouse button after dragging."""
        if self.selected:
            self.canvas.itemconfig(self.selected, width=3, outline='blue')
            self.update_coordinates(self.selected)
        self.selected = None
        self.selected_vertex = None
        self.startxy = None

    def on_right_click(self, event):
        """Handle right-click events to finish polygon creation or delete polygons."""
        if self.creating_polygon:
            self.finish_polygon_creation()
            return
        items = self.canvas.find_overlapping(event.x-10, event.y-10, event.x+10, event.y+10)
        for item in items:
            for idx, (polygon_id, _, vertex_ids) in enumerate(self.polygons):
                if item == polygon_id:
                    msg = messagebox.askyesnocancel('Info', 'Mark selected polygon as deleted?')
                    if msg:
                        self.canvas.delete(polygon_id)
                        for vertex_id in vertex_ids:
                            self.canvas.delete(vertex_id)
                        self.polygons = [(p_id, p, v_ids) for p_id, p, v_ids in self.polygons if p_id != polygon_id]
                        self.mongo_handler.delete_polygon(idx)
                        # Update indices of remaining polygons in the database
                        for new_idx, (p_id, points, v_ids) in enumerate(self.polygons):
                            self.mongo_handler.save_polygon(new_idx, points)
                        if self.selected == polygon_id:
                            self.selected = None
                        self.coord_text.delete(1.0, tk.END)
                        self.coord_text.insert(tk.END, "Selected polygon marked as deleted.\n")
                        if self.video_image_id:
                            self.canvas.tag_lower(self.video_image_id)
                        self.canvas.update()
                    return

    def update_coordinates(self, polygon_id=None):
        """Update the coordinate display for the selected polygon."""
        if not polygon_id or polygon_id not in [p_id for p_id, _, _ in self.polygons]:
            return
        self.coord_text.delete(1.0, tk.END)
        for idx, (p_id, points, _) in enumerate(self.polygons):
            if p_id == polygon_id:
                self.coord_text.insert(tk.END, f"Polygon-{idx} Points:\n")
                for i in range(0, len(points), 2):
                    self.coord_text.insert(tk.END, f"Point {i//2 + 1}: ({points[i]:.2f}, {points[i+1]:.2f})\n")
                break

    def clear_all(self):
        """Mark all polygons as deleted and clear the canvas."""
        msg = messagebox.askyesnocancel('Info', 'Mark all polygons as deleted?')
        if msg:
            self.canvas.delete('polygon', 'vertex')  # Delete only polygons and vertices
            self.polygons = []
            self.selected = None
            self.creating_polygon = False
            self.temp_points = []
            if self.temp_polygon_id:
                self.canvas.delete(self.temp_polygon_id)
                self.temp_polygon_id = None
            self.person_tracker.clear()
            self.mongo_handler.mark_all_polygons_deleted()
            self.coord_text.delete(1.0, tk.END)
            self.coord_text.insert(tk.END, "All polygons marked as deleted.\n")
            if hasattr(self, 'current_photo') and self.current_photo and not self.video_image_id:
                self.video_image_id = self.canvas.create_image(0, 0, image=self.current_photo, anchor='nw', tags='video')
            if self.video_image_id:
                self.canvas.tag_lower(self.video_image_id)
            self.canvas.update()

    def destroy(self):
        """Clean up resources and close the application."""
        self.video_running = False
        if hasattr(self, 'cap'):
            self.cap.release()
        self.mongo_handler.close()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = PolygonApp(root)
    root.mainloop()
