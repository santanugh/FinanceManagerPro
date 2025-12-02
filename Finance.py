
import flet as ft
import sqlite3
import datetime
import os
import sys
import logging
import traceback
import calendar
import platform
import subprocess
import ctypes
import updater_utils
import threading
import winreg
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT

import winreg

def update_registry_version(version):
    """
    Updates the Windows 'Add/Remove Programs' entry to match the current running version.
    """
    # This ID matches your Inno Setup script exactly (The '{{' becomes '{')
    APP_ID = "{A3B4C5D6-E7F8-9012-3456-7890ABCDEF12}"
    
    try:
        # Inno Setup appends "_is1" to the AppId for the registry key
        key_path = f"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_ID}_is1"
        
        # Try to open the key in HKEY_CURRENT_USER (Since you used {localappdata})
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        except FileNotFoundError:
            logger.info("Registry key not found. (If running locally/debug, this is normal)")
            return

        with key:
            # Update the 'DisplayVersion' value
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
            logger.info(f"SUCCESS: Control Panel version updated to {version}")
            
    except Exception as e:
        logger.error(f"Registry Update Failed: {e}")

# --- WINDOWS TASKBAR ICON FIX ---
try:
    myappid = 'santanu.financemanager.pro.1.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

# --- CONFIGURATION & PATHS ---
import sys
import os

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Use standard paths for data that needs to be written (Database/Logs)
# We store this in the same folder where the EXE is running
EXE_LOCATION = os.path.dirname(os.path.abspath(sys.argv[0])) 

# Database config
DB_FILENAME = "finance.db"
DB_FILE = os.path.join(EXE_LOCATION, DB_FILENAME)

# Assets config (Logos moved to assets folder)
SCRIPT_DIR = resource_path(".")
LOGO_FILENAME = "logo.png"
LOGO_ICO_FILENAME = "logo.ico"

# These paths are for ReportLab (PDF generation) which needs absolute OS paths
LOGO_FULL_PATH = os.path.join(SCRIPT_DIR, "assets", LOGO_FILENAME)
LOGO_ICO_FULL_PATH = os.path.join(SCRIPT_DIR, "assets", LOGO_ICO_FILENAME)

# --- LOGGING ---
log_dir = os.path.join(EXE_LOCATION, "logs")
try:
    os.makedirs(log_dir, exist_ok=True)
except OSError as e:
    print(f"CRITICAL ERROR: Failed to create log directory '{log_dir}': {e}")

log_file_name = f"finance_app_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
log_filename = os.path.join(log_dir, log_file_name)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
try:
    file_handler = logging.FileHandler(log_filename, 'w', 'utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
except Exception as e:
    print(f"CRITICAL ERROR: Failed to create log file handler: {e}")

class LoggerWriter:
    def __init__(self, level): self.level = level
    def write(self, message):
        if message.strip(): self.level(message.strip())
    def flush(self): pass

sys.stdout = LoggerWriter(logger.info)
sys.stderr = LoggerWriter(logger.error)

logger.info("--- Application Started ---")
logger.info(f"Script Directory: {SCRIPT_DIR}")
logger.info(f"Logo Path (PNG): {LOGO_FULL_PATH}")
logger.info(f"Logo Path (ICO): {LOGO_ICO_FULL_PATH}")

# --- BACKEND LOGIC ---
def initialize_database():
    logger.info("Initializing database...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_datetime TEXT NOT NULL,
            type TEXT NOT NULL,
            comment TEXT,
            amount REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def clean_comment_sql(column_name="comment"):
    return f"LOWER(TRIM(REPLACE(REPLACE({column_name}, '\n', ''), '\r', '')))"

def add_transaction_db(datetime_str, trans_type, comment, amount):
    logger.info(f"Adding transaction: {trans_type}, {amount}")
    try:
        if trans_type in ['Base Expense', 'Borrow']:
            amount = -abs(amount)
        else:
            amount = abs(amount)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO transactions (transaction_datetime, type, comment, amount) VALUES (?, ?, ?, ?)",
            (datetime_str, trans_type, comment, amount)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return False

def get_summary_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
        SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS total_deposits,
        SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) AS total_expenditure
        FROM transactions
    ''')
    result = cursor.fetchone()
    conn.close()
    return result[0] or 0.0, result[1] or 0.0

def get_unique_comments():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        query = f"SELECT DISTINCT {clean_comment_sql()} FROM transactions WHERE comment IS NOT NULL ORDER BY 1"
        cursor.execute(query)
        records = cursor.fetchall()
        conn.close()
        return [row[0].title() for row in records if row[0]]
    except Exception as e:
        logger.error(f"Error fetching comments: {e}")
        return []

def get_available_years():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT strftime('%Y', transaction_datetime) FROM transactions ORDER BY 1 DESC")
        years = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()
        if not years:
            return [str(datetime.datetime.now().year)]
        return years
    except Exception as e:
        logger.error(f"Error fetching years: {e}")
        return [str(datetime.datetime.now().year)]

def get_recent_transactions(limit=10):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, transaction_datetime, type, comment, amount FROM transactions ORDER BY transaction_datetime DESC LIMIT ?", (limit,))
    data = cursor.fetchall()
    conn.close()
    return data

def get_chart_data():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    clean_col = clean_comment_sql('comment')
    query = f'''
        SELECT {clean_col}, ABS(SUM(amount))
        FROM transactions
        WHERE amount < 0
        GROUP BY {clean_col}
        ORDER BY ABS(SUM(amount)) DESC
        LIMIT 5
    '''
    cursor.execute(query)
    data = cursor.fetchall()
    conn.close()
    return data

def get_filtered_transactions(start_date, end_date, trans_type, comment_like):
    logger.info(f"Filtering: {start_date} to {end_date}, Type: {trans_type}, Comment: {comment_like}")
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        query = "SELECT transaction_datetime, type, comment, amount, id FROM transactions WHERE 1=1"
        params = []
        if start_date:
            query += " AND DATE(transaction_datetime) >= ?"
            params.append(start_date)
        if end_date:
            query += " AND DATE(transaction_datetime) <= ?"
            params.append(end_date)
        if trans_type and trans_type != "All":
            query += " AND type = ?"
            params.append(trans_type)
        if comment_like and comment_like != "All":
            query += f" AND {clean_comment_sql()} LIKE ?"
            params.append(f"%{comment_like.lower()}%")
        query += " ORDER BY transaction_datetime DESC"
        cursor.execute(query, params)
        records = cursor.fetchall()
        conn.close()
        return records
    except Exception as e:
        logger.error(f"Filter error: {e}")
        return []

def get_summary_by_comment():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        query = f"""
            SELECT {clean_comment_sql()} AS clean_comment, type, SUM(amount), COUNT(id)
            FROM transactions GROUP BY clean_comment, type ORDER BY SUM(amount) ASC
        """
        cursor.execute(query)
        records = cursor.fetchall()
        conn.close()
        return records
    except Exception as e:
        logger.error(f"Summary error: {e}")
        return []

# --- MODERN PDF GENERATOR ---
def draw_canvas_elements(canvas, doc):
    """Draws Watermark AND Page Border"""
    try:
        canvas.saveState()
        page_width, page_height = letter

        canvas.setStrokeColor(colors.black)
        canvas.setLineWidth(2)
        canvas.rect(20, 20, page_width - 40, page_height - 40)

        if os.path.exists(LOGO_FULL_PATH):
            canvas.setFillAlpha(0.1)
            image_width = 300
            image_height = 300
            x = (page_width - image_width) / 2
            y = (page_height - image_height) / 2
            canvas.drawImage(LOGO_FULL_PATH, x, y, width=image_width, height=image_height, mask='auto', preserveAspectRatio=True)
        canvas.restoreState()
    except Exception as e:
        logger.warning(f"Canvas error: {e}")

def generate_modern_pdf(filename, data_dict):
    try:
        doc = SimpleDocTemplate(filename, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=20, alignment=TA_LEFT, spaceAfter=5, textColor=colors.darkblue)
        header_name_style = ParagraphStyle('Name', parent=styles['Heading1'], fontSize=24, alignment=TA_LEFT, spaceAfter=2, textColor=colors.black)

        text_col = [
            Paragraph("Santanu Ghosh", header_name_style),
            Spacer(1, 6),
            Paragraph(data_dict.get("title", "Finance Report"), title_style)
        ]
        if os.path.exists(LOGO_FULL_PATH):
            logo_img = RLImage(LOGO_FULL_PATH, width=60, height=60)
            header_table = Table([[logo_img, text_col]], colWidths=[70, 400])
            header_table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
            ]))
            elements.append(header_table)
        else:
            elements.extend(text_col)

        elements.append(Spacer(1, 10))

        filter_info = data_dict.get("filter_info", "")
        if filter_info:
            p_filter = Paragraph(f"<b>REPORT CONTEXT:</b> {filter_info}", styles['Normal'])
            t_filter = Table([[p_filter]], colWidths=[480])
            t_filter.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.aliceblue),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('PADDING', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(t_filter)
            elements.append(Spacer(1, 20))

        summary_data = data_dict.get("summary", [])
        if summary_data:
            elements.append(Paragraph("<b>Summary Overview</b>", styles['Heading3']))
            elements.append(Spacer(1, 5))
            t_sum = Table(summary_data, hAlign='LEFT', colWidths=[200, 150])
            t_sum.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.darkgrey),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ]))
            elements.append(t_sum)
            elements.append(Spacer(1, 25))

        cat_headers = data_dict.get("cat_headers", [])
        cat_rows = data_dict.get("cat_rows", [])
        if cat_headers and cat_rows:
            elements.append(Paragraph("<b>Category Breakdown</b>", styles['Heading3']))
            elements.append(Spacer(1, 10))
            cat_table_data = [cat_headers] + cat_rows
            t_cat = Table(cat_table_data, repeatRows=1, colWidths=[200, 100, 60, 120])
            cat_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkslategray),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ])
            for i, row in enumerate(cat_rows):
                bg_color = colors.white if i % 2 == 0 else colors.whitesmoke
                cat_style.add('BACKGROUND', (0, i+1), (-1, i+1), bg_color)
            t_cat.setStyle(cat_style)
            elements.append(t_cat)
            elements.append(Spacer(1, 25))

        headers = data_dict.get("headers", [])
        rows = data_dict.get("rows", [])
        if headers and rows:
            elements.append(Paragraph("<b>Transaction Details</b>", styles['Heading3']))
            elements.append(Spacer(1, 10))
            table_data = [headers] + rows
            t = Table(table_data, repeatRows=1, colWidths=[120, 100, 160, 100])
            main_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkslategray),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ])
            for i, row in enumerate(rows):
                bg_color = colors.white if i % 2 == 0 else colors.whitesmoke
                main_style.add('BACKGROUND', (0, i+1), (-1, i+1), bg_color)
            t.setStyle(main_style)
            elements.append(t)

        doc.build(elements, onFirstPage=draw_canvas_elements, onLaterPages=draw_canvas_elements)
        logger.info(f"PDF Generated: {filename}")
        return True
    except Exception as e:
        logger.error(f"PDF Error: {e}")
        traceback.print_exc()
        return False

# --- UI COMPONENTS ---
class StatCard(ft.Container):
    def __init__(self, title, value, icon_name, icon_hex, bg_hex):
        super().__init__()
        self.padding = 20
        self.border_radius = 12
        self.bgcolor = bg_hex
        self.expand = True
        self.content = ft.Row([
            ft.Container(
                content=ft.Icon(name=icon_name, color="white", size=32),
                padding=12,
                bgcolor="#30000000",
                border_radius=12
            ),
            ft.Column([
                ft.Text(title, size=14, weight="bold", color="white", opacity=0.9),
                ft.Text(value, size=26, weight="bold", font_family="Roboto Mono", color="white")
            ], spacing=2, alignment="center")
        ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER)

class MiniStat(ft.Container):
    def __init__(self, label, value, color):
        super().__init__()
        self.padding = 10
        self.bgcolor = "#2C2C2C"
        self.border_radius = 8
        self.expand = True
        self.content = ft.Column([
            ft.Text(label, size=10, color="grey"),
            ft.Text(value, size=16, weight="bold", color=color, font_family="Roboto Mono")
        ], spacing=2)

# --- MAIN APP ---
def main(page: ft.Page):
    # SYNC REGISTRY VERSION
    # This ensures Control Panel shows the correct version after an auto-update
    update_registry_version(updater_utils.CURRENT_VERSION)

    # ... (rest of your main code) ...
    page.title = "Finance Manager Pro"
    page.theme_mode = "dark"
    page.padding = 0
    page.window_width = 1300
    page.window_height = 900
    page.fonts = {"Roboto Mono": "https://github.com/google/fonts/raw/main/apache/robotomono/RobotoMono%5Bwght%5D.ttf"}

    # --- UPDATE BUTTON (Hidden by default) ---
    update_button = ft.ElevatedButton(
        text="Update Available",
        icon="system_update",
        bgcolor="#FFD700",  # Gold color
        color="black",
        visible=False,      # Hidden until update found
        height=35,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
    )

    # --- TOP APP BAR ---
    page.appbar = ft.AppBar(
        leading=ft.Icon("account_balance_wallet", color="#2196F3", size=30), # FIXED HERE
        leading_width=40,
        title=ft.Text("Finance Manager Pro", weight="bold", color="white", size=20),
        center_title=False,
        bgcolor="#1f1f1f",
        actions=[
            ft.Container(content=update_button, padding=ft.padding.only(right=20))
        ]
    )

    # --- APP ICON (absolute path for Windows reliability) ---
    try:
        ico_abs = LOGO_ICO_FULL_PATH
        png_abs = LOGO_FULL_PATH

        if platform.system() == "Windows" and os.path.exists(ico_abs):
            page.window.icon = ico_abs  # absolute path to .ico (Windows-only effect)
            logger.info(f"Window icon set to absolute path (ICO): {ico_abs}")
        elif os.path.exists(png_abs):
            page.window.icon = png_abs  # absolute path (may not show in Windows title bar)
            logger.info(f"Window icon set to absolute path (PNG): {png_abs}")
        else:
            logger.warning("No logo.ico/logo.png found for window icon.")
    except Exception as e:
        logger.warning(f"Icon set failed: {e}")

    # --- CLOSURE LOGGING ---
    page.window.prevent_close = True
    def on_window_event(e):
        if e.data == "close":
            logger.info("--- Application Closed by User ---")
            page.window.destroy()
    page.window.on_event = on_window_event

    initialize_database()

    app_state = {"chart_data": [], "touched_index": -1}

# --- UPDATE CHECKER LOGIC ---
    def check_for_update_on_startup():
        try:
            result = updater_utils.check_for_updates()
            
            if result and result[0]:
                download_url, version_tag, file_size = result
                
                def on_update_click(e):
                    import shutil
                    import subprocess
                    import sys
                    import ctypes
                    
                    # 1. EXTRACT UPDATER
                    try:
                        updater_src = resource_path(os.path.join("assets", "updater.exe"))
                        updater_dest = os.path.join(os.path.dirname(sys.executable), "updater_tool.exe")
                        shutil.copy(updater_src, updater_dest)
                    except: return

                    # 2. CREATE BATCH LAUNCHER
                    bat_content = f"""
@echo off
timeout /t 1 >nul
start "" "{updater_dest}" "{download_url}" "{version_tag}" "{sys.executable}"
del "%~f0"
"""
                    launcher_bat = "launch.bat"
                    with open(launcher_bat, "w") as f:
                        f.write(bat_content)

                    # 3. HIDE WINDOW INSTANTLY (Fixes Black Screen Freeze)
                    page.window.visible = False
                    page.update()

                    # 4. RUN BATCH & HARD KILL
                    os.startfile(launcher_bat)
                    logger.info("Batch launched. Killing Main App.")
                    
                    ctypes.windll.kernel32.ExitProcess(0)

                # SHOW BUTTON
                update_button.text = f"Update Available ({version_tag})"
                update_button.on_click = on_update_click
                update_button.visible = True
                update_button.update()
                
        except Exception as e:
            logger.error(f"Update UI Error: {e}")

    # --- Helpers ---
    def handle_date_picked(e, text_field):
        if e.control.value:
            text_field.value = e.control.value.strftime("%Y-%m-%d")
            text_field.update()

    def handle_time_picked(e, text_field):
        if e.control.value:
            text_field.value = e.control.value.strftime("%H:%M")
            text_field.update()

    def open_file_externally(path):
        try:
            if platform.system() == 'Windows':
                os.startfile(path)
            elif platform.system() == 'Darwin':
                subprocess.call(('open', path))
            else:
                subprocess.call(('xdg-open', path))
        except Exception as e:
            logger.error(f"Failed to open file: {e}")

    # --- SAVE DIALOG & STATE ---
    save_state = {"data_dict": {}, "filename": "Report.pdf"}

    def show_msg(message, is_error=False, open_path=None):
        bg_color = "#D32F2F" if is_error else "#2E7D32"
        icon_name = "error_outline" if is_error else "check_circle"
        if open_path:
            bg_color = "#1565C0"
            icon_name = "description"
        content = ft.Row([
            ft.Icon(name=icon_name, color="white"),
            ft.Text(value=message, color="white", weight="bold", size=14)
        ], alignment="start", spacing=10)
        action_text = "OPEN" if open_path else None
        snack = ft.SnackBar(
            content=content,
            bgcolor=bg_color,
            action=action_text,
            action_color="#FFD700",
            on_action=lambda _: open_file_externally(open_path) if open_path else None,
            show_close_icon=True,
            close_icon_color="white",
            behavior=ft.SnackBarBehavior.FLOATING,
            shape=ft.RoundedRectangleBorder(radius=8),
            margin=ft.margin.all(15),
            duration=6000 if open_path else 3000
        )
        page.open(snack)

    def save_file_result(e: ft.FilePickerResultEvent):
        if e.path:
            file_path = e.path
            if not file_path.lower().endswith(".pdf"):
                file_path += ".pdf"
            logger.info(f"Saving PDF to: {file_path}")
            if generate_modern_pdf(file_path, save_state["data_dict"]):
                show_msg("PDF Saved Successfully!", open_path=file_path)
            else:
                show_msg("PDF Generation Failed", is_error=True)

    save_file_dialog = ft.FilePicker(on_result=save_file_result)
    page.overlay.append(save_file_dialog)

    # --- GLOBAL UI ELEMENTS ---
    card_balance = StatCard("Balance", "₹0.00", "account_balance_wallet", "#FFFFFF", "#1565C0")
    card_income = StatCard("Income", "₹0.00", "arrow_upward", "#FFFFFF", "#2E7D32")
    card_expense = StatCard("Expense", "₹0.00", "arrow_downward", "#FFFFFF", "#C62828")

    expense_chart = ft.PieChart(sections=[], sections_space=2, center_space_radius=40, expand=True)

    dashboard_table = ft.DataTable(columns=[
        ft.DataColumn(ft.Text("Date")), ft.DataColumn(ft.Text("Type")),
        ft.DataColumn(ft.Text("Comment")), ft.DataColumn(ft.Text("Amount", weight="bold")),
    ], heading_row_color="#424242")

    type_dropdown = ft.Dropdown(
        label="Type",
        options=[ft.dropdown.Option("Deposit"), ft.dropdown.Option("Base Expense"), ft.dropdown.Option("Borrow")],
        value="Deposit",
        width=400
    )
    comment_input = ft.TextField(label="Comment", width=400)
    amount_input = ft.TextField(label="Amount", width=400, keyboard_type="number", prefix_text="₹ ")

    now = datetime.datetime.now()
    date_input = ft.TextField(label="Date", value=now.strftime("%Y-%m-%d"), width=150, read_only=True)
    time_input = ft.TextField(label="Time", value=now.strftime("%H:%M"), width=150, read_only=True)

    date_picker_add = ft.DatePicker(
        on_change=lambda e: handle_date_picked(e, date_input),
        first_date=datetime.datetime(2020, 1, 1),
        last_date=datetime.datetime(2030, 12, 31)
    )
    time_picker_add = ft.TimePicker(on_change=lambda e: handle_time_picked(e, time_input))
    page.overlay.extend([date_picker_add, time_picker_add])

    # --- HISTORY ELEMENTS ---
    filter_mode = ft.RadioGroup(content=ft.Row([
        ft.Radio(value="all", label="All Time"), ft.Radio(value="month", label="Month"),
        ft.Radio(value="year", label="Year"), ft.Radio(value="3_months", label="Last 3 Months"),
        ft.Radio(value="6_months", label="Last 6 Months"), ft.Radio(value="range", label="Date Range")
    ], scroll="auto"))
    filter_mode.value = "all"

    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    current_year = str(datetime.datetime.now().year)
    available_years = get_available_years()
    sel_month = ft.Dropdown(options=[ft.dropdown.Option(m) for m in months],
                            value=months[datetime.datetime.now().month-1], width=130, dense=True, label="Month")
    sel_year = ft.Dropdown(options=[ft.dropdown.Option(y) for y in available_years], value=current_year, width=100, dense=True, label="Year")
    container_month = ft.Row([sel_month, sel_year], visible=False)
    sel_year_only = ft.Dropdown(options=[ft.dropdown.Option(y) for y in available_years], value=current_year, width=120, dense=True, label="Select Year")
    container_year = ft.Row([sel_year_only], visible=False)

    filter_start = ft.TextField(label="Start Date", width=130, height=40, text_size=12, read_only=True)
    filter_end = ft.TextField(label="End Date", width=130, height=40, text_size=12, read_only=True)
    date_picker_start = ft.DatePicker(on_change=lambda e: handle_date_picked(e, filter_start))
    date_picker_end = ft.DatePicker(on_change=lambda e: handle_date_picked(e, filter_end))
    page.overlay.extend([date_picker_start, date_picker_end])

    container_range = ft.Row([
        ft.Row([filter_start, ft.IconButton(icon="calendar_today", on_click=lambda _: page.open(date_picker_start), icon_size=18)], spacing=2),
        ft.Row([filter_end, ft.IconButton(icon="calendar_today", on_click=lambda _: page.open(date_picker_end), icon_size=18)], spacing=2),
    ], visible=False)

    filter_type = ft.Dropdown(
        label="Type",
        options=[ft.dropdown.Option("All"), ft.dropdown.Option("Deposit"), ft.dropdown.Option("Base Expense"), ft.dropdown.Option("Borrow")],
        value="All", width=130, text_size=12, content_padding=10, dense=True
    )
    filter_comment = ft.Dropdown(label="Comment", options=[ft.dropdown.Option("All")], value="All", width=180, text_size=12, content_padding=10, dense=True)

    history_table_full = ft.DataTable(columns=[
        ft.DataColumn(ft.Text("Date")), ft.DataColumn(ft.Text("Type")),
        ft.DataColumn(ft.Text("Comment")), ft.DataColumn(ft.Text("Amount", weight="bold"))
    ], heading_row_color="#424242")

    sidebar_balance = ft.Container()
    sidebar_income = ft.Container()
    sidebar_expense = ft.Container()
    sidebar_breakdown_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Comment")), ft.DataColumn(ft.Text("Type")),
            ft.DataColumn(ft.Text("Cnt"), numeric=True), ft.DataColumn(ft.Text("Amount"), numeric=True)
        ],
        column_spacing=10, heading_row_height=30, data_row_min_height=30,
        heading_text_style=ft.TextStyle(size=12, weight="bold"), data_text_style=ft.TextStyle(size=11)
    )

    report_output = ft.TextField(
        multiline=True, read_only=True,
        text_style=ft.TextStyle(font_family="Courier New", size=14, color="#00FF00"),
        bgcolor="#111111", expand=True
    )

    # --- LOGIC FUNCTIONS ---
    def update_chart_sections(touched_index):
        sections = []
        colors_list = ["#9C27B0", "#2196F3", "#009688", "#FF9800", "#F44336"]
        if not app_state["chart_data"]:
            return [ft.PieChartSection(1, title="No Data", color="grey", radius=45)]
        for i, (cat, amt) in enumerate(app_state["chart_data"]):
            is_touched = (i == touched_index)
            radius = 55 if is_touched else 45
            cat_name = (cat or "Misc").strip().title()
            badge = None
            if is_touched:
                badge = ft.Container(
                    content=ft.Text(f"{cat_name}\n₹{amt:,.2f}", color="white", size=12, weight="bold", text_align="center"),
                    bgcolor="#2C2C2C", padding=8, border_radius=6, border=ft.border.all(1, "#555555")
                )
            sections.append(ft.PieChartSection(
                amt, title="" if is_touched else f"{cat_name[:10]}",
                color=colors_list[i % len(colors_list)],
                radius=radius,
                title_style=ft.TextStyle(size=10, weight=ft.FontWeight.BOLD, color="white"),
                badge=badge, badge_position=1.0
            ))
        return sections

    def on_pie_touch(e: ft.PieChartEvent):
        idx = e.section_index if e.section_index is not None else -1
        if idx != app_state["touched_index"]:
            app_state["touched_index"] = idx
            expense_chart.sections = update_chart_sections(idx)
            expense_chart.update()
    expense_chart.on_chart_event = on_pie_touch

    def refresh_dashboard():
        dep, exp = get_summary_stats()
        card_balance.content.controls[1].controls[1].value = f"₹{(dep+exp):,.2f}"
        card_income.content.controls[1].controls[1].value = f"₹{dep:,.2f}"
        card_expense.content.controls[1].controls[1].value = f"₹{abs(exp):,.2f}"

        recent_data = get_recent_transactions(8)
        new_rows = []
        for row in recent_data:
            dt, typ, cmt, amt = row[1], row[2], row[3], row[4]
            cmt = (cmt or "").strip().title()
            color = "#EF5350" if amt < 0 else "#66BB6A"
            new_rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(dt[:10])), ft.DataCell(ft.Text(typ)),
                ft.DataCell(ft.Text(cmt)), ft.DataCell(ft.Text(f"₹{amt:,.2f}", color=color, weight="bold"))
            ]))
        dashboard_table.rows = new_rows

        app_state["chart_data"] = get_chart_data()
        expense_chart.sections = update_chart_sections(-1)
        page.update()

    def update_filter_comments(force_update=False):
        comments = ["All"] + get_unique_comments()
        filter_comment.options = [ft.dropdown.Option(c) for c in comments]
        if force_update:
            filter_comment.update()

    def update_sidebar_ui(transactions_data):
        agg = {}
        total_dep = 0.0
        total_exp = 0.0
        for row in transactions_data:
            _, t_type, cmt, amt, _ = row
            cmt = (cmt or "N/A").replace("\n", "").replace("\r", "").strip().title()
            if amt > 0: total_dep += amt
            else: total_exp += amt
            key = (cmt, t_type)
            if key not in agg: agg[key] = [0, 0.0]
            agg[key][0] += 1
            agg[key][1] += amt

        net = total_dep + total_exp
        sidebar_balance.content = MiniStat("Balance", f"₹{net:,.2f}", "#FFFFFF")
        sidebar_income.content = MiniStat("Deposits", f"₹{total_dep:,.2f}", "#66BB6A")
        sidebar_expense.content = MiniStat("Expense", f"₹{total_exp:,.2f}", "#EF5350")

        table_rows = []
        for k in sorted(agg.keys(), key=lambda k: agg[k][1]):
            comm, typ = k
            count, total = agg[k]
            color = "#EF5350" if total < 0 else "#66BB6A"
            table_rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(comm, size=11, weight="bold")),
                ft.DataCell(ft.Text(typ, size=10)),
                ft.DataCell(ft.Text(str(count), size=11)),
                ft.DataCell(ft.Text(f"{total:,.0f}", color=color, size=11, weight="bold"))
            ]))
        sidebar_breakdown_table.rows = table_rows

        if sidebar_balance.page:
            sidebar_balance.update()
            sidebar_income.update()
            sidebar_expense.update()
            sidebar_breakdown_table.update()

    def toggle_filter_visibility(e):
        mode = filter_mode.value
        container_month.visible = (mode == "month")
        container_year.visible = (mode == "year")
        container_range.visible = (mode == "range")
        page.update()
        run_filter(None)
    filter_mode.on_change = toggle_filter_visibility

    def run_filter(e):
        mode = filter_mode.value
        start_val = None; end_val = None; today = datetime.datetime.now()
        if mode == "month":
            try:
                m_index = months.index(sel_month.value) + 1
                y_val = int(sel_year.value)
                start_val = datetime.date(y_val, m_index, 1).strftime("%Y-%m-%d")
                last_day = calendar.monthrange(y_val, m_index)[1]
                end_val = datetime.date(y_val, m_index, last_day).strftime("%Y-%m-%d")
            except:
                pass
        elif mode == "year":
            y_val = int(sel_year_only.value)
            start_val = f"{y_val}-01-01"; end_val = f"{y_val}-12-31"
        elif mode == "3_months":
            start_val = (today - datetime.timedelta(days=90)).strftime("%Y-%m-%d"); end_val = today.strftime("%Y-%m-%d")
        elif mode == "6_months":
            start_val = (today - datetime.timedelta(days=180)).strftime("%Y-%m-%d"); end_val = today.strftime("%Y-%m-%d")
        elif mode == "range":
            start_val = filter_start.value; end_val = filter_end.value

        data = get_filtered_transactions(start_val, end_val, filter_type.value, filter_comment.value)
        new_rows = []
        for row in data:
            dt, typ, cmt, amt, _ = row
            cmt = (cmt or "N/A").strip().title()
            color = "#EF5350" if amt < 0 else "#66BB6A"
            new_rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(dt[:16])), ft.DataCell(ft.Text(typ)),
                ft.DataCell(ft.Text(cmt.title())), ft.DataCell(ft.Text(f"₹{amt:,.2f}", color=color, weight="bold"))
            ]))
        history_table_full.rows = new_rows
        update_sidebar_ui(data)
        if history_table_full.page:
            history_table_full.update()

    def save_history_pdf_click(e):
        mode = filter_mode.value; start_val = None; end_val = None; today = datetime.datetime.now()
        context_str_parts = []
        if mode == "all": context_str_parts.append("All Time History")
        elif mode == "month":
            try:
                m_index = months.index(sel_month.value) + 1
                y_val = int(sel_year.value)
                start_val = datetime.date(y_val, m_index, 1).strftime("%Y-%m-%d")
                last_day = calendar.monthrange(y_val, m_index)[1]
                end_val = datetime.date(y_val, m_index, last_day).strftime("%Y-%m-%d")
                context_str_parts.append(f"Month: {sel_month.value} {y_val}")
            except:
                pass
        elif mode == "year":
            y_val = int(sel_year_only.value)
            start_val = f"{y_val}-01-01"; end_val = f"{y_val}-12-31"; context_str_parts.append(f"Financial Year: {y_val}")
        elif mode == "3_months":
            start_val = (today - datetime.timedelta(days=90)).strftime("%Y-%m-%d"); end_val = today.strftime("%Y-%m-%d"); context_str_parts.append("Last 3 Months")
        elif mode == "6_months":
            start_val = (today - datetime.timedelta(days=180)).strftime("%Y-%m-%d"); end_val = today.strftime("%Y-%m-%d"); context_str_parts.append("Last 6 Months")
        elif mode == "range":
            start_val = filter_start.value; end_val = filter_end.value; context_str_parts.append(f"Range: {start_val} to {end_val}")

        if filter_type.value != "All": context_str_parts.append(f"Type: {filter_type.value}")
        if filter_comment.value != "All": context_str_parts.append(f"Category: {filter_comment.value}")

        data = get_filtered_transactions(start_val, end_val, filter_type.value, filter_comment.value)
        agg = {}; total_dep = 0.0; total_exp = 0.0; pdf_rows = []
        for row in data:
            dt, typ, cmt, amt, _ = row
            cmt = (cmt or "N/A").replace("\n", "").strip().title()
            if amt > 0: total_dep += amt
            else: total_exp += amt
            key = (cmt, typ)
            if key not in agg: agg[key] = [0, 0.0]
            agg[key][0] += 1; agg[key][1] += amt
            pdf_rows.append([dt[:16], typ, cmt, f"{amt:,.2f}"])

        cat_rows = []
        for k in sorted(agg.keys(), key=lambda x: agg[x][1]):
            cat_rows.append([k[0], k[1], str(agg[k][0]), f"{agg[k][1]:,.2f}"])

        summary_list = [
            ("Date Generated", today.strftime('%Y-%m-%d %H:%M')),
            ("Total Records", str(len(pdf_rows))),
            ("Total Deposits", f"Rs. {total_dep:,.2f}"),
            ("Total Expenditure", f"Rs. {total_exp:,.2f}"),
            ("Net Balance", f"Rs. {(total_dep+total_exp):,.2f}")
        ]

        save_state["data_dict"] = {
            "title": "Transaction History Report",
            "filter_info": " \n ".join(context_str_parts),
            "summary": summary_list,
            "cat_headers": ["Category", "Type", "Cnt", "Amount"],
            "cat_rows": cat_rows,
            "headers": ["Date", "Type", "Comment", "Amount"],
            "rows": pdf_rows
        }
        save_file_dialog.save_file(file_name=f"Transactions_{today.strftime('%Y-%m-%d-%H-%M-%S')}.pdf", allowed_extensions=["pdf"])

    # --- FIXED: Generate View (aligned text report) ---
    def generate_report_click(e):
        records = get_summary_by_comment()

        header = f"{'Comment':<25} {'Type':<12} {'Cnt':>3} {'Amount':>12}"
        lines = []
        lines.append("---- Category Summary Report ----")
        lines.append("-" * len(header))
        lines.append(header)
        lines.append("-" * len(header))

        total_dep = 0.0
        total_exp = 0.0

        for rec in records:
            comm, r_type, total, count = rec
            name = (comm or "N/A").title()
            if len(name) > 25:
                name = name[:24] + "…"
            lines.append(f"{name:<25} {r_type:<12} {count:>3} {total:>12.2f}")

            if total > 0:
                total_dep += total
            else:
                total_exp += total

        lines.append("=" * len(header))
        lines.append(f"{'Total Deposits:':<40}{total_dep:>12.2f}")
        lines.append(f"{'Total Expenditure:':<40}{total_exp:>12.2f}")
        lines.append(f"{'Remaining Balance:':<40}{(total_dep + total_exp):>12.2f}")

        report_output.value = "\n".join(lines)
        report_output.update()

    # --- RESTORED: Add Transaction handler ---
    def add_transaction_click(e):
        try:
            if not amount_input.value:
                show_msg("Enter amount", is_error=True); return
            if not date_input.value or not time_input.value:
                show_msg("Date & Time required", is_error=True); return

            amt = float(amount_input.value)
            dt_str = f"{date_input.value} {time_input.value}"
            try:
                datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            except ValueError:
                show_msg("Invalid Date/Time", is_error=True); return

            if add_transaction_db(dt_str, type_dropdown.value, comment_input.value, amt):
                show_msg("Transaction Saved!")
                amount_input.value = ""; comment_input.value = ""
                now_reset = datetime.datetime.now()
                date_input.value = now_reset.strftime("%Y-%m-%d")
                time_input.value = now_reset.strftime("%H:%M")
                page.update()
            else:
                show_msg("Database Error", is_error=True)
        except ValueError:
            show_msg("Invalid Amount", is_error=True)

    def save_report_pdf_click(e):
        records = get_summary_by_comment(); total_dep = 0.0; total_exp = 0.0; pdf_rows = []
        for rec in records:
            comm, r_type, total, count = rec
            comm = (comm or "N/A").title()
            if total > 0: total_dep += total
            else: total_exp += total
            pdf_rows.append([comm, r_type, str(count), f"{total:,.2f}"])

        summary_list = [
            ("Date Generated", datetime.datetime.now().strftime('%Y-%m-%d %H:%M')),
            ("Total Deposits", f"Rs. {total_dep:,.2f}"),
            ("Total Expenditure", f"Rs. {total_exp:,.2f}"),
            ("Net Balance", f"Rs. {(total_dep+total_exp):,.2f}")
        ]
        save_state["data_dict"] = {
            "title": "Category Summary Report", "filter_info": "All Time Category Aggregation",
            "summary": summary_list, "headers": ["Category", "Type", "Count", "Total Amount"], "rows": pdf_rows
        }
        save_file_dialog.save_file(file_name=f"Summary_{datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.pdf", allowed_extensions=["pdf"])

    # --- LAYOUT ---
    view_dashboard = ft.Container(content=ft.Column([
        ft.Text("Dashboard", size=30, weight="bold"),
        ft.Row([card_balance, card_income, card_expense], spacing=20),
        ft.Divider(color="transparent", height=20),
        ft.Row([
            ft.Container(content=ft.Column([
                ft.Text("Recent Transactions", size=18, weight="bold"),
                ft.Column([dashboard_table], scroll="auto", expand=True)
            ], expand=True),
            expand=7, height=400, bgcolor="#1f1f1f", border_radius=15, padding=20),
            ft.Container(content=ft.Column([
                ft.Text("Expense Breakdown", size=18, weight="bold"),
                expense_chart
            ], horizontal_alignment="center", expand=True),
            expand=3, height=400, bgcolor="#1f1f1f", border_radius=15, padding=20)
        ], spacing=20, expand=True)
    ], scroll="auto"), padding=20, expand=True)

    view_add = ft.Container(content=ft.Column([
        ft.Icon("add_card", size=60, color="#2196F3"),
        ft.Text("Add Transaction", size=24, weight="bold"),
        ft.Divider(height=10, color="transparent"),
        ft.Row([
            ft.Row([date_input, ft.IconButton(icon="calendar_month", on_click=lambda _: page.open(date_picker_add))], spacing=0),
            ft.Row([time_input, ft.IconButton(icon="access_time", on_click=lambda _: page.open(time_picker_add))], spacing=0)
        ], alignment="center", spacing=20),
        type_dropdown, comment_input, amount_input,
        ft.Divider(height=20, color="transparent"),
        ft.ElevatedButton("Save Transaction", on_click=add_transaction_click, height=50, width=400)
    ], horizontal_alignment="center", spacing=15), alignment=ft.alignment.center, expand=True)

    view_transactions = ft.Container(content=ft.Row([
        ft.Container(content=ft.Column([
            ft.Text("Transaction History", size=24, weight="bold"),
            filter_mode, ft.Divider(height=10, color="transparent"),
            container_month, container_year, container_range,
            ft.Row([
                filter_type, filter_comment,
                ft.IconButton("search", on_click=run_filter, bgcolor="#1976D2", tooltip="Apply Filters"),
                ft.IconButton("picture_as_pdf", on_click=save_history_pdf_click, bgcolor="#C62828", tooltip="Export Current View")
            ], spacing=10, wrap=True),
            ft.Column(controls=[history_table_full], scroll="auto", expand=True)
        ], expand=True), expand=7, padding=10),
        ft.VerticalDivider(width=1, color="grey"),
        ft.Container(content=ft.Column([
            ft.Text("Live Summary", size=20, weight="bold", color="#90CAF9"),
            ft.Divider(height=10),
            ft.Row([sidebar_income, sidebar_expense], spacing=10),
            ft.Container(height=10),
            sidebar_balance,
            ft.Divider(height=30),
            ft.Text("Breakdown", size=16, weight="bold"),
            ft.Column(controls=[sidebar_breakdown_table], scroll="auto", expand=True)
        ], expand=True), expand=3, bgcolor="#1f1f1f", padding=15, border_radius=10)
    ], expand=True), padding=10, expand=True)

    view_reports = ft.Container(content=ft.Column([
        ft.Text("Detailed Report", size=24, weight="bold"),
        ft.Row([
            ft.ElevatedButton("Generate View", icon="visibility", on_click=generate_report_click),
            ft.ElevatedButton("Save as PDF", icon="save_alt", on_click=save_report_pdf_click, bgcolor="#C62828")
        ]),
        ft.Divider(),
        report_output
    ], expand=True), padding=20, expand=True)

    main_area = ft.Container(content=view_dashboard, expand=True)

    def nav_change(e):
        idx = e.control.selected_index
        if idx == 0:
            refresh_dashboard()
            main_area.content = view_dashboard
        elif idx == 1:
            main_area.content = view_add
        elif idx == 2:
            update_filter_comments(force_update=False)
            run_filter(None)
            main_area.content = view_transactions
        elif idx == 3:
            main_area.content = view_reports
        page.update()

    nav_logo = ft.Container(content=ft.Image(src=LOGO_FILENAME, width=50, height=50), padding=10) if os.path.exists(LOGO_FULL_PATH) else None
    rail = ft.NavigationRail(
        selected_index=0, label_type="all", group_alignment=-0.9, leading=nav_logo,
        destinations=[
            ft.NavigationRailDestination(icon="dashboard", label="Home"),
            ft.NavigationRailDestination(icon="add_circle", label="Add"),
            ft.NavigationRailDestination(icon="list", label="History"),
            ft.NavigationRailDestination(icon="analytics", label="Report")
        ],
        on_change=nav_change
    )

    page.add(ft.Row([rail, ft.VerticalDivider(width=1), main_area], expand=True))
    timer = threading.Timer(2.0, check_for_update_on_startup)
    timer.start()
    refresh_dashboard()
    logger.info("UI Initialized")

if __name__ == "__main__":
    try:
        # Ensure assets are served from the script folder
        ft.app(target=main, assets_dir="assets")
    except Exception as e:
        logger.critical(f"FATAL CRASH: {e}", exc_info=True)
        logging.shutdown()
        traceback.print_exc()
