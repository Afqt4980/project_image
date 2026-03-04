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
        self.root.geometry("1000x650") 
        self.root.configure(bg="#f0f0f0")

        # 1. ตั้งค่า AI และข้อมูลเริ่มต้น
        print("กำลังเตรียมความพร้อม AI YOLO-World...")
        self.model = YOLO('yolov8s-world.pt')
        self.cap = cv2.VideoCapture(0)
        
        self.db_filename = "products_db.json"
        self.product_dict = self.load_database()
        
        # ส่งเฉพาะ List ของคำภาษาอังกฤษไปให้ AI ค้นหา
        if self.product_dict:
            self.model.set_classes(list(self.product_dict.keys()))
        else:
            self.model.set_classes(["object"]) # ค่าเริ่มต้นกัน AI error
        
        self.current_counts = {}       
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
            # เริ่มต้นให้เป็น Dictionary ว่างๆ เพื่อให้ผู้ใช้เพิ่มเอง
            default_data = {} 
            with open(self.db_filename, 'w', encoding='utf-8') as file:
                json.dump(default_data, file, ensure_ascii=False, indent=4)
            return default_data

    def save_to_database(self):
        with open(self.db_filename, 'w', encoding='utf-8') as file:
            json.dump(self.product_dict, file, ensure_ascii=False, indent=4)

    # ---------------------------------------------

    def setup_ui(self):
        # --- Frame ด้านซ้าย (Sidebar Menu) ---
        self.sidebar = tk.Frame(self.root, bg="#2c3e50", width=200)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        
        tk.Label(self.sidebar, text="เมนูจัดการ", fg="white", bg="#2c3e50", font=("Arial", 16, "bold")).pack(pady=20)

        btn_style = {"font": ("Arial", 12), "bg": "#34495e", "fg": "white", "width": 18, "pady": 10, "bd": 0}
        
        tk.Button(self.sidebar, text="📦 สินค้าทั้งหมด", command=self.show_all_products_window, **btn_style).pack(pady=5)
        tk.Button(self.sidebar, text="➕ เพิ่มสินค้าใหม่", command=self.add_new_product_popup, **btn_style).pack(pady=5)
        # นำปุ่มเซฟภาพบรรยากาศออกตามความต้องการ
        
        tk.Button(self.sidebar, text="📊 บันทึกยอดลง Excel", command=self.export_to_excel, bg="#27ae60", fg="white", font=("Arial", 12), width=18, pady=10, bd=0).pack(pady=30)

        # --- Frame ด้านขวา (หน้าหลัก - Main View) ---
        self.main_view = tk.Frame(self.root, bg="#ffffff")
        self.main_view.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)
        
        tk.Label(self.main_view, text="หน้านับสินค้า (ตรวจจับหลายชนิดพร้อมกัน)", font=("Arial", 18, "bold"), bg="#ffffff").pack(pady=10)

        self.canvas = tk.Canvas(self.main_view, width=640, height=480, bg="black")
        self.canvas.pack()

        self.result_label = tk.Label(self.main_view, text="กำลังวิเคราะห์...", font=("Arial", 14), bg="#ffffff", fg="blue")
        self.result_label.pack(pady=10)

        tk.Button(self.main_view, text="💾 บันทึกยอดนับ 'ชุดนี้' เข้าระบบ", command=self.save_current_set, font=("Arial", 14, "bold"), bg="#f39c12", fg="white", padx=20, pady=5).pack()

    # --- ฟังก์ชันการทำงานของเมนูต่างๆ ---

    def show_all_products_window(self):
        """หน้าต่างแสดงสินค้าทั้งหมดแบบมีรูปภาพและเลื่อนได้"""
        if not self.product_dict:
            messagebox.showinfo("แจ้งเตือน", "ยังไม่มีสินค้าในระบบ กรุณาเพิ่มสินค้าใหม่")
            return

        window = tk.Toplevel(self.root)
        window.title("รายการสินค้าทั้งหมด")
        window.geometry("500x600")
        window.configure(bg="#f9f9f9")
        window.grab_set()

        tk.Label(window, text="รายการสินค้าในระบบ", font=("Arial", 16, "bold"), bg="#f9f9f9").pack(pady=10)

        # สร้าง Canvas และ Scrollbar เพื่อให้เลื่อนดูได้
        canvas = tk.Canvas(window, bg="#f9f9f9", highlightthickness=0)
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#f9f9f9")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # เก็บภาพไว้กัน Garbage Collector ลบ
        self.product_images = []

        # วนลูปแสดงสินค้าแต่ละรายการ
        for ai_prompt, prod_name in self.product_dict.items():
            item_frame = tk.Frame(scrollable_frame, bg="white", bd=1, relief="solid")
            item_frame.pack(fill="x", padx=10, pady=5)

            # พยายามโหลดภาพ
            img_path = os.path.join("product_samples", f"{ai_prompt.replace(' ', '_')}.jpg")
            if os.path.exists(img_path):
                img = Image.open(img_path)
                img = img.resize((100, 100), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.product_images.append(photo) # เก็บ reference ไว้
                
                img_label = tk.Label(item_frame, image=photo, bg="white")
                img_label.pack(side="left", padx=10, pady=10)
            else:
                # ถ้าไม่มีภาพ แสดงกล่องข้อความแทน
                no_img_label = tk.Label(item_frame, text="ไม่มีภาพ", width=12, height=6, bg="#e0e0e0")
                no_img_label.pack(side="left", padx=10, pady=10)

            # แสดงรายละเอียด
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
                
            # --- ส่วนบันทึกภาพตัวอย่าง (อัปเดตแก้บั๊กแล้ว) ---
            if self.latest_raw_frame is not None and self.latest_raw_frame.size > 0:
                try:
                    save_dir = "product_samples"
                    if not os.path.exists(save_dir):
                        os.makedirs(save_dir) 
                    
                    safe_filename = f"{ai_prompt.replace(' ', '_')}.jpg"
                    filepath = os.path.join(save_dir, safe_filename)
                    
                    # ลดขนาดภาพลงครึ่งนึงเพื่อไม่ให้ไฟล์ใหญ่เกินไป
                    resized_img = cv2.resize(self.latest_raw_frame, (320, 240))
                    cv2.imwrite(filepath, resized_img)
                except Exception as e:
                    print(f"เกิดข้อผิดพลาดในการเซฟรูป: {e}")
            
            # อัปเดตข้อมูล
            self.product_dict[ai_prompt] = prod_name
            self.save_to_database()
            self.model.set_classes(list(self.product_dict.keys())) 
            
            messagebox.showinfo("สำเร็จ", f"เพิ่มสินค้า '{prod_name}'\nและบันทึกลงฐานข้อมูลสำเร็จ!", parent=popup)
            popup.destroy() 
            
        tk.Button(popup, text="📸 บันทึกข้อมูลพร้อมเซฟภาพตัวอย่าง", command=save_product, font=("Arial", 12, "bold"), bg="#2980b9", fg="white", pady=10).pack(pady=20)

    def save_current_set(self):
        # เช็กว่ามีสินค้าถูกนับไหม และในระบบมีสินค้าหรือยัง
        if not self.product_dict:
             messagebox.showwarning("แจ้งเตือน", "ยังไม่มีสินค้าในระบบ กรุณาเพิ่มสินค้าก่อน")
             return
             
        if sum(self.current_counts.values()) == 0:
            if not messagebox.askyesno("ยืนยัน", "ไม่พบสินค้าในกล้องเลย คุณต้องการบันทึกข้อมูลเป็น 0 ใช่หรือไม่?"):
                return
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        set_data = {"เวลา (Time)": timestamp}
        
        for ai_prompt, count in self.current_counts.items():
            display_name = self.product_dict.get(ai_prompt, ai_prompt)
            set_data[display_name] = count
            
        self.saved_sets.append(set_data)
        messagebox.showinfo("บันทึกสำเร็จ", f"บันทึกข้อมูลชุดที่ {len(self.saved_sets)} เรียบร้อยแล้ว!")

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
            
            # ถ้าไม่มีสินค้าในระบบ ให้ข้ามการ predict ไปก่อน
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
                self.result_label.config(text=f"ตรวจพบ: {result_text}")

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

# หมายเหตุ:
# - โค้ดนี้เป็นระบบตรวจจับและนับสินค้าด้วย AI YOLO-World ที่มีการจัดการฐานข้อมูลแบบ JSON และฟีเจอร์การบันทึกยอดนับลง Excel (CSV) ได้อย่างครบถ้วน
# - ผู้ใช้สามารถเพิ่มสินค้าใหม่ได้ด้วยการกรอกชื่อและลักษณะเด่นที่ AI จะรู้จัก พร้อมกับบันทึกภาพตัวอย่างอัตโนมัติ
# - มีการจัดการข้อผิดพลาดและการแจ้งเตือนผู้ใช้ในกรณีต่างๆ เพื่อให้ใช้งานได้ง่ายและไม่เกิดปัญหาในการใช้งานจริง