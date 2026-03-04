import cv2
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
from ultralytics import YOLO
import csv
import os
import json 
from datetime import datetime

class InventoryAIApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ระบบ AI ตรวจจับและนับสินค้าอัจฉริยะ")
        self.root.geometry("1200x700") # ขยายหน้าต่างให้กว้างขึ้นเพื่อรองรับระบบตะกร้า
        self.root.configure(bg="#f0f0f0")

        print("กำลังเตรียมความพร้อม AI YOLO-World...")
        self.model = YOLO('yolov8s-world.pt')
        self.cap = cv2.VideoCapture(0)
        
        self.db_filename = "products_db.json"
        self.product_dict = self.load_database()
        
        if self.product_dict:
            self.model.set_classes(list(self.product_dict.keys()))
        else:
            self.model.set_classes(["object"]) 
        
        self.current_counts = {}       # ตัวเลขเรียลไทม์จากกล้อง
        self.current_tally = {}        # [อัปเดต] ตัวเลขใน "ตะกร้า" ที่ให้ผู้ใช้ปรับแก้ได้
        self.saved_sets = []           
        self.latest_annotated_frame = None 
        self.latest_raw_frame = None   

        self.setup_ui()
        self.update_frame() 

    # --- ฟังก์ชันจัดการฐานข้อมูล (JSON Database) ---
    def load_database(self):
        if os.path.exists(self.db_filename):
            with open(self.db_filename, 'r', encoding='utf-8') as file:
                return json.load(file)
        else:
            default_data = {} 
            with open(self.db_filename, 'w', encoding='utf-8') as file:
                json.dump(default_data, file, ensure_ascii=False, indent=4)
            return default_data

    def save_to_database(self):
        with open(self.db_filename, 'w', encoding='utf-8') as file:
            json.dump(self.product_dict, file, ensure_ascii=False, indent=4)

    # ---------------------------------------------

    def setup_ui(self):
        # --- Frame ด้านซ้ายสุด (Sidebar Menu) ---
        self.sidebar = tk.Frame(self.root, bg="#2c3e50", width=200)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        
        tk.Label(self.sidebar, text="เมนูจัดการ", fg="white", bg="#2c3e50", font=("Arial", 16, "bold")).pack(pady=20)

        btn_style = {"font": ("Arial", 12), "bg": "#34495e", "fg": "white", "width": 18, "pady": 10, "bd": 0}
        tk.Button(self.sidebar, text="📦 สินค้าทั้งหมด", command=self.show_all_products_window, **btn_style).pack(pady=5)
        tk.Button(self.sidebar, text="➕ เพิ่มสินค้าใหม่", command=self.add_new_product_popup, **btn_style).pack(pady=5)
        tk.Button(self.sidebar, text="📊 ส่งออกรายงาน Excel", command=self.export_to_excel, bg="#27ae60", fg="white", font=("Arial", 12), width=18, pady=10, bd=0).pack(pady=30)

        # --- Frame หน้าหลัก (Main View) แบ่งซ้าย-ขวา ---
        self.main_view = tk.Frame(self.root, bg="#ffffff")
        self.main_view.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)
        
        tk.Label(self.main_view, text="หน้านับสินค้าอัจฉริยะ (AI Scanner)", font=("Arial", 18, "bold"), bg="#ffffff").pack(pady=10)

        content_frame = tk.Frame(self.main_view, bg="#ffffff")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 1. โซนกล้อง (ซ้าย)
        camera_frame = tk.Frame(content_frame, bg="#ffffff")
        camera_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(camera_frame, width=640, height=480, bg="black")
        self.canvas.pack()

        self.result_label = tk.Label(camera_frame, text="กำลังวิเคราะห์...", font=("Arial", 14), bg="#ffffff", fg="blue")
        self.result_label.pack(pady=10)

        # [ปุ่มใหม่] ดึงของลงตะกร้า
        tk.Button(camera_frame, text="📥 1. ดึงจำนวนจากกล้องลงตะกร้า", command=self.add_camera_to_tally, font=("Arial", 14, "bold"), bg="#3498db", fg="white", padx=20, pady=10).pack(pady=5)

        # 2. โซนตะกร้า (ขวา)
        cart_frame = tk.Frame(content_frame, bg="#ecf0f1", bd=2, relief="groove")
        cart_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10)

        tk.Label(cart_frame, text="🛒 ตะกร้าสินค้า (แก้ไขได้)", font=("Arial", 16, "bold"), bg="#ecf0f1").pack(pady=10)

        self.tally_list_frame = tk.Frame(cart_frame, bg="#ecf0f1")
        self.tally_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.refresh_tally_ui() # โหลด UI ตะกร้าครั้งแรก

        # [ปุ่มบันทึกชุด]
        tk.Button(cart_frame, text="💾 2. บันทึกตะกร้าเข้าระบบ", command=self.save_current_set, font=("Arial", 14, "bold"), bg="#f39c12", fg="white", padx=20, pady=10).pack(side=tk.BOTTOM, pady=20)

    # --- ระบบตะกร้าสินค้า (Tally System) ---
    def add_camera_to_tally(self):
        added = False
        for ai_prompt, count in self.current_counts.items():
            if count > 0:
                self.current_tally[ai_prompt] = self.current_tally.get(ai_prompt, 0) + count
                added = True
        
        if added:
            self.refresh_tally_ui()
        else:
            messagebox.showinfo("แจ้งเตือน", "ไม่พบสินค้าในกล้องขณะนี้")

    def update_tally(self, ai_prompt, delta):
        if ai_prompt in self.current_tally:
            self.current_tally[ai_prompt] += delta
            if self.current_tally[ai_prompt] <= 0:
                del self.current_tally[ai_prompt] # ลบออกถ้าเหลือน้อยกว่า 1
            self.refresh_tally_ui()

    def remove_from_tally(self, ai_prompt):
        if ai_prompt in self.current_tally:
            del self.current_tally[ai_prompt]
            self.refresh_tally_ui()

    def refresh_tally_ui(self):
        """รีเฟรชหน้าต่างตะกร้าเพื่อสร้างปุ่ม บวกลบ และลบ"""
        # ล้างของเก่าทิ้งก่อนวาดใหม่
        for widget in self.tally_list_frame.winfo_children():
            widget.destroy()

        if not self.current_tally:
            tk.Label(self.tally_list_frame, text="ยังไม่มีสินค้าในตะกร้า", bg="#ecf0f1", fg="gray", font=("Arial", 12)).pack(pady=20)
            return

        for ai_prompt, count in self.current_tally.items():
            row = tk.Frame(self.tally_list_frame, bg="white", bd=1, relief="solid")
            row.pack(fill=tk.X, padx=10, pady=5)

            display_name = self.product_dict.get(ai_prompt, ai_prompt)
            
            # ชื่อสินค้า
            tk.Label(row, text=display_name, font=("Arial", 12, "bold"), bg="white", width=15, anchor="w").pack(side=tk.LEFT, padx=10, pady=10)
            
            # ปุ่มลบ 1
            tk.Button(row, text=" - ", command=lambda p=ai_prompt: self.update_tally(p, -1), font=("Arial", 12, "bold"), bg="#e74c3c", fg="white", width=3).pack(side=tk.LEFT, padx=5)
            # ตัวเลขนับ
            tk.Label(row, text=str(count), font=("Arial", 14, "bold"), bg="white", width=4).pack(side=tk.LEFT)
            # ปุ่มบวก 1
            tk.Button(row, text=" + ", command=lambda p=ai_prompt: self.update_tally(p, 1), font=("Arial", 12, "bold"), bg="#2ecc71", fg="white", width=3).pack(side=tk.LEFT, padx=5)
            # ปุ่มทิ้ง (ลบทั้งหมด)
            tk.Button(row, text=" 🗑️ ทิ้ง ", command=lambda p=ai_prompt: self.remove_from_tally(p), font=("Arial", 10), bg="#95a5a6", fg="white").pack(side=tk.RIGHT, padx=10)

    def save_current_set(self):
        if not self.current_tally:
            messagebox.showwarning("แจ้งเตือน", "ไม่มีสินค้าในตะกร้า กรุณาดึงข้อมูลจากกล้องก่อน")
            return
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        set_data = {"เวลา (Time)": timestamp}
        
        for ai_prompt, count in self.current_tally.items():
            display_name = self.product_dict.get(ai_prompt, ai_prompt)
            set_data[display_name] = count
            
        self.saved_sets.append(set_data)
        messagebox.showinfo("บันทึกสำเร็จ", f"บันทึกข้อมูลชุดที่ {len(self.saved_sets)} เรียบร้อยแล้ว!")
        
        # ล้างตะกร้าหลังบันทึกเสร็จ
        self.current_tally.clear()
        self.refresh_tally_ui()

    # --- ฟังก์ชันการทำงานอื่นๆ (เหมือนเดิม) ---

    def show_all_products_window(self):
        if not self.product_dict:
            messagebox.showinfo("แจ้งเตือน", "ยังไม่มีสินค้าในระบบ กรุณาเพิ่มสินค้าใหม่")
            return

        window = tk.Toplevel(self.root)
        window.title("รายการสินค้าทั้งหมด")
        window.geometry("500x600")
        window.configure(bg="#f9f9f9")
        window.grab_set()

        tk.Label(window, text="รายการสินค้าในระบบ", font=("Arial", 16, "bold"), bg="#f9f9f9").pack(pady=10)

        canvas = tk.Canvas(window, bg="#f9f9f9", highlightthickness=0)
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#f9f9f9")

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.product_images = []

        for ai_prompt, prod_name in self.product_dict.items():
            item_frame = tk.Frame(scrollable_frame, bg="white", bd=1, relief="solid")
            item_frame.pack(fill="x", padx=10, pady=5)

            img_path = os.path.join("product_samples", f"{ai_prompt.replace(' ', '_')}.jpg")
            if os.path.exists(img_path):
                img = Image.open(img_path)
                img = img.resize((100, 100), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.product_images.append(photo) 
                
                img_label = tk.Label(item_frame, image=photo, bg="white")
                img_label.pack(side="left", padx=10, pady=10)
            else:
                no_img_label = tk.Label(item_frame, text="ไม่มีภาพ", width=12, height=6, bg="#e0e0e0")
                no_img_label.pack(side="left", padx=10, pady=10)

            details_frame = tk.Frame(item_frame, bg="white")
            details_frame.pack(side="left", fill="both", expand=True, padx=10)
            
            tk.Label(details_frame, text=prod_name, font=("Arial", 14, "bold"), bg="white", anchor="w").pack(fill="x", pady=(10, 0))
            tk.Label(details_frame, text=f"AI Prompt: {ai_prompt}", font=("Arial", 10), fg="gray", bg="white", anchor="w").pack(fill="x")

    def add_new_product_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("เพิ่มสินค้าใหม่")
        popup.geometry("400x350")
        popup.configure(bg="#f9f9f9")
        popup.grab_set() 
        
        tk.Label(popup, text="กรุณานำสินค้ามาวางหน้ากล้อง", font=("Arial", 12, "bold"), bg="#f9f9f9", fg="red").pack(pady=10)
        
        tk.Label(popup, text="1. ชื่อสินค้า (สำหรับแสดงผล/Excel):", bg="#f9f9f9", font=("Arial", 10)).pack(pady=5)
        name_entry = tk.Entry(popup, width=35, font=("Arial", 12))
        name_entry.pack(pady=5)
        name_entry.insert(0, "ตัวอย่าง: ขวดน้ำสีเหลือง")
        
        tk.Label(popup, text="2. ลักษณะเด่น (ภาษาอังกฤษให้ AI รู้จัก):", bg="#f9f9f9", font=("Arial", 10)).pack(pady=5)
        prompt_entry = tk.Entry(popup, width=35, font=("Arial", 12))
        prompt_entry.pack(pady=5)
        prompt_entry.insert(0, "ตัวอย่าง: yellow bottle")
        
        def save_product():
            prod_name = name_entry.get().strip()
            ai_prompt = prompt_entry.get().strip().lower()
            
            if not prod_name or not ai_prompt or "ตัวอย่าง:" in prod_name or "ตัวอย่าง:" in ai_prompt:
                messagebox.showwarning("แจ้งเตือน", "กรุณากรอกข้อมูลให้ครบและถูกต้อง", parent=popup)
                return
                
            if ai_prompt in self.product_dict:
                messagebox.showwarning("แจ้งเตือน", "ลักษณะเด่น (AI Prompt) นี้มีในระบบแล้ว", parent=popup)
                return
                
            if self.latest_raw_frame is not None and self.latest_raw_frame.size > 0:
                try:
                    save_dir = "product_samples"
                    if not os.path.exists(save_dir):
                        os.makedirs(save_dir) 
                    
                    safe_filename = f"{ai_prompt.replace(' ', '_')}.jpg"
                    filepath = os.path.join(save_dir, safe_filename)
                    
                    resized_img = cv2.resize(self.latest_raw_frame, (320, 240))
                    cv2.imwrite(filepath, resized_img)
                except Exception as e:
                    print(f"เกิดข้อผิดพลาดในการเซฟรูป: {e}")
            
            self.product_dict[ai_prompt] = prod_name
            self.save_to_database()
            self.model.set_classes(list(self.product_dict.keys())) 
            
            messagebox.showinfo("สำเร็จ", f"เพิ่มสินค้า '{prod_name}'\nและบันทึกลงฐานข้อมูลสำเร็จ!", parent=popup)
            popup.destroy() 
            
        tk.Button(popup, text="📸 บันทึกข้อมูลพร้อมเซฟภาพตัวอย่าง", command=save_product, font=("Arial", 12, "bold"), bg="#2980b9", fg="white", pady=10).pack(pady=20)

    def export_to_excel(self):
        if not self.saved_sets:
            messagebox.showwarning("แจ้งเตือน", "ยังไม่มีข้อมูลถูกบันทึกในระบบ")
            return
            
        filename = f"inventory_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        fieldnames = ["เวลา (Time)"] + list(self.product_dict.values())
        
        try:
            with open(filename, mode='w', newline='', encoding='utf-8-sig') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                for data_set in self.saved_sets:
                    row_data = {key: data_set.get(key, 0) for key in fieldnames}
                    writer.writerow(row_data)
            messagebox.showinfo("สำเร็จ", f"ส่งออกข้อมูลไปยัง '{filename}' เรียบร้อยแล้ว!\n(สามารถดับเบิ้ลคลิกเปิดด้วย Excel ได้เลย)")
        except Exception as e:
            messagebox.showerror("ข้อผิดพลาด", f"ไม่สามารถสร้างไฟล์ได้: {e}")

    # --- ฟังก์ชันประมวลผลกล้องและ AI ---

    def update_frame(self):
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.resize(frame, (640, 480))
            self.latest_raw_frame = frame.copy() 
            
            if self.product_dict:
                results = self.model.predict(frame, conf=0.25, verbose=False)
                
                self.current_counts = {prompt: 0 for prompt in self.product_dict.keys()}
                names = results[0].names 
                
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    ai_prompt = names[cls_id]
                    if ai_prompt in self.current_counts:
                        self.current_counts[ai_prompt] += 1

                result_texts = []
                for ai_prompt, count in self.current_counts.items():
                    if count > 0:
                        display_name = self.product_dict.get(ai_prompt, ai_prompt)
                        result_texts.append(f"{display_name}: {count}")
                        
                result_text = " | ".join(result_texts)
                if not result_text:
                    result_text = "ไม่พบสินค้าในรายการ"
                self.result_label.config(text=f"ตรวจพบตอนนี้: {result_text}")

                annotated_frame = results[0].plot()
            else:
                 self.result_label.config(text="ยังไม่มีสินค้าในระบบ กรุณาเพิ่มสินค้า")
                 annotated_frame = frame
                 
            self.latest_annotated_frame = annotated_frame 
            
            cv_img = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
            self.photo = ImageTk.PhotoImage(image=Image.fromarray(cv_img))
            self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)

        self.root.after(15, self.update_frame)

    def __del__(self):
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()

if __name__ == "__main__":
    root = tk.Tk()
    app = InventoryAIApp(root)
    root.mainloop()