import pdfplumber #Reads PDFs and extracts text.
import re #For regular expressions 
import os #For file handling
import csv #Exploring data
from playwright.sync_api import sync_playwright #Automatic web browser

# === CONFIGURATION ===
PDF_FOLDER = "pdfs" #The folder that contains the wanted PDFs
TARGET_URL = "https://nahdi-frfvx5xzdhpl-je.integration.ocp.oraclecloud.com/ic/builder/rt/NahdiAjeerProgramApp/live/webApps/nahdiajeerprogram/" #The targeted web form URL
HEADLESS = False #False = browser UI is visiable, True = runs in background
USER_DATA_DIR = "user_data" #Save sessio. So that the user won't need to log in evert time
# =====================

#=====================METHOD 1=====================
#Opnes the PDF 
#Joins text from all pages into a single String 
#"or " "" = ensure no error when the page has no text
def extract_pdf_data(pdf_path):
    """Extract Ajeer ID, Issue Date, and Expiry Date from reversed Arabic PDF"""
    #=====================1=====================
    with pdfplumber.open(pdf_path) as pdf:
        #=====================2=====================
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        #===========================================

#Remove spaces and right-to-left markers. "\u200f" for easier regex markers
    text = text.replace(" ", "").replace("\u200f", "")

#Reguler Expression to find:
#TQ followed by >= 5  = Ajeer ID
#Dates in YYYY-MM-DD format followed by Arabic labels = Issue Dates
    #=====================3=====================
    ajeer_id_match = re.search(r"TQ\d{5,}", text)
    issue_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})ﺢﻳﺮﺼﺘﻟاﺔﻳاﺪﺑﺦﻳرﺎﺗ", text)
    expiry_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})ﺢﻳﺮﺼﺘﻟاﺔﻳﺎﻬﻧﺦﻳرﺎﺗ", text)

#If any data is missing, it prints the first 800 characters of the PDF for debugging and raises and error
    #=====================4=====================
    if not (ajeer_id_match and issue_match and expiry_match):
        print("=== DEBUG START ===")
        print(text[:800])
        print("=== DEBUG END ===")
        raise ValueError(f"⚠️ Missing required data in {pdf_path}")

#Returns extracted data as a tuple: (Ajeer ID, Issue Date, Expiry Date)
    #=====================5=====================
    return ajeer_id_match.group(0), issue_match.group(1), expiry_match.group(1)

#=====================METHOD 2=====================
#Debgging tool for inspecting shadow DOM elements, often used in Oracle JET components
#Check if the file input exists inside a shadowRoot
def debug_shadow_dom(page):
    """Debug helper to inspect shadow DOM structure"""
    shadow_info = page.evaluate("""
        () => {
            const picker = document.querySelector('oj-file-picker');
            if (!picker) return 'oj-file-picker not found';
            
            let info = 'Found oj-file-picker\\n';
            if (picker.shadowRoot) {
                info += 'Has shadowRoot\\n';
                const input = picker.shadowRoot.querySelector('input[type="file"]');
                info += input ? 'Has file input in shadow' : 'No file input found';
            } else {
                info += 'No shadowRoot';
            }
            return info;
        }
    """)
    print(f"🔍 Shadow DOM Info:\n{shadow_info}")

#=====================METHOD 3=====================
#Main automation function: opens page, fills form, upload PDFs, submits
def fill_web_form(context, employee_id, ajeer_id, issue_date, expiry_date, pdf_path):
    """Automate the form fill and upload (reuses persistent browser context)"""
    #=====================1=====================
    #Opens a new browser tab and navigates to the URL
    page = context.new_page()
    #===========================================

    print(f"\n🌐 Navigating to {TARGET_URL} ...")
    #Waits for the network to be idle (Page fully loaded)
    page.goto(TARGET_URL, wait_until="networkidle")
    #Waits an additional 3 second for safety
    page.wait_for_timeout(3000)

    # === STEP 1: Fill Employee ID and trigger form expansion ===
    #Find employee field and fills it
    print("\n📝 STEP 1: Filling Employee ID...")
    #=====================2=====================
    try:
        #Use \\| to escape the character |
        page.wait_for_selector('input#field-1\\|input', timeout=15000, state="visible")
        
        # Fill the field
        employee_input = page.locator('input#field-1\\|input')
        #=====================3=====================
        employee_input.fill(employee_id)
        print(f"✅ Employee ID filled: {employee_id}")
        
        # More aggressive event triggering
        #Runs JavaScript to trigger multiple events on the input (IMPORTANT for validation in Oracle JET forms)
        #=====================4 =====================
        page.evaluate("""
            (empId) => {
                const input = document.querySelector('input#field-1\\\\|input');
                if (input) {
                    // Set value directly
                    input.value = empId;
                    
                    // Trigger all possible events
                    ['input', 'change', 'keyup', 'keydown', 'blur', 'focus'].forEach(eventType => {
                        input.dispatchEvent(new Event(eventType, { bubbles: true }));
                    });
                    
                    // Special handling for Oracle JET components
                    const ojInput = input.closest('oj-input-text');
                    if (ojInput) {
                        ojInput.dispatchEvent(new CustomEvent('ojValueChanged', {
                            detail: { value: empId },
                            bubbles: true
                        }));
                    }
                }
            }
        """, employee_id)
        #===========================================
        print("⏳ Waiting for validation...")
        page.wait_for_timeout(3000)
        
        # Click somewhere else to trigger blur (important for validation)
        #=====================5=====================
        page.evaluate("() => document.body.click()")
        #===========================================
        page.wait_for_timeout(1000)
        #=====================6=====================
    except Exception as e:
        print(f"❌ Error filling Employee ID: {e}")
        page.screenshot(path="step1_error.png")
        input("Fill Employee ID manually, then press ENTER...")

    # === STEP 2: Click "Get Employee Info" to reveal other fields ===
    print("\n🖱️ STEP 2: Clicking 'Get Employee Info' button...")
    try:
        # Wait for button to appear 
        page.wait_for_selector('#oj-button-get-info', timeout=10000)
        print("✅ Button found")
        #Forces it to be clickable
        print("🔧 Force-enabling button...")
        # Force-enable the button
        force_enabled = page.evaluate("""
            () => {
                const btn = document.querySelector('#oj-button-get-info');
                if (btn) {
                    btn.removeAttribute('disabled');
                    const innerBtn = btn.querySelector('button');
                    if (innerBtn) innerBtn.removeAttribute('disabled');
                    return true;
                }
                return false;
            }
        """)
        
        if force_enabled:
            print("✅ Button force-enabled")
            page.wait_for_timeout(500)
        else:
            print("❌ Could not force-enable button")
            raise Exception("Button could not be enabled")
        
        #Clicks on the button using JS if normal click fails
        page.evaluate("""
            () => {
                const ojButton = document.querySelector('#oj-button-get-info');
                if (ojButton) {
                    const innerBtn = ojButton.querySelector('button');
                    if (innerBtn) {
                        innerBtn.click();
                    } else {
                        ojButton.click();
                    }
                }
            }
        """)
        
        print("✅ Button clicked! Waiting for form to update...")
        page.wait_for_timeout(4000)
        
    except Exception as e:
        print(f"⚠️ Button click error: {e}")
        page.screenshot(path="button_error.png")
        print("👆 Click the 'Get Employee Info' button manually")
        input("Press ENTER after clicking...")

    # === STEP 3: Wait for and fill the remaining fields ===
    print("\n📝 STEP 3: Filling remaining fields...")
    
    # Debug: Check how many inputs exist now
    input_count = page.evaluate("() => document.querySelectorAll('input[type=\"text\"]').length")
    print(f"🔍 Now found {input_count} text input fields")
    
    try:
        # Wait for field-3 to appear (Ajeer ID)
        #Fill Ajeer ID
        print("⏳ Waiting for Ajeer ID field...")
        page.wait_for_selector('input#field-3\\|input', timeout=10000, state="visible")
        page.fill('input#field-3\\|input', ajeer_id)
        print(f"✅ Ajeer ID: {ajeer_id}")
        
        # Fill Issue Date
        #Fill Issue Date
        print("⏳ Waiting for Issue Date field...")
        page.wait_for_selector('input#field-4\\|input', timeout=5000, state="visible")
        page.fill('input#field-4\\|input', issue_date)
        print(f"✅ Issue Date: {issue_date}")
        
        # Fill Expiry Date
        #Fill Expiry Date Field
        print("⏳ Waiting for Expiry Date field...")
        page.wait_for_selector('input#field-5\\|input', timeout=5000, state="visible")
        page.fill('input#field-5\\|input', expiry_date)
        print(f"✅ Expiry Date: {expiry_date}")
        
        # Trigger validation on all fields
        #Trigger blur and change events for validation
        page.evaluate("""
            () => {
                document.querySelectorAll('input').forEach(input => {
                    input.dispatchEvent(new Event('blur', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                });
            }
        """)
        page.wait_for_timeout(1000)
        print("✅ All fields filled successfully!")
        
    except Exception as e:
        print(f"❌ Error filling remaining fields: {e}")
        page.screenshot(path="fields_error.png")
        print("\n🔍 Available input fields:")
        fields_debug = page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('input')).map(i => ({
                    id: i.id,
                    type: i.type,
                    visible: i.offsetParent !== null
                }));
            }
        """)
        for f in fields_debug:
            print(f"  - ID: {f['id']}, Type: {f['type']}, Visible: {f['visible']}")
        input("Fill remaining fields manually, then press ENTER...")

    # === STEP 4: Upload PDF ===
    print("\n📎 STEP 4: Uploading PDF...")
    
    # Wait a moment for upload field to appear
    page.wait_for_timeout(2000)
    
    uploaded = False

    #3 Mithods t omake the upload reliable
    # Method 1: File chooser event (most reliable for Oracle JET)
    try:
        print("🔍 Attempting file chooser...")
        with page.expect_file_chooser(timeout=10000) as fc_info:
            # Try different text variations
            try:
                page.get_by_text("Add Files").click(timeout=3000)
            except:
                try:
                    page.get_by_text("Drag and Drop").click(timeout=3000)
                except:
                    page.get_by_text("Add Files. Drag and Drop.").click(timeout=3000)
        
        file_chooser = fc_info.value
        file_chooser.set_files(pdf_path)
        print(f"✅ Uploaded via file chooser")
        uploaded = True
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"❌ File chooser failed: {e}")

    # Method 2: Look for oj-file-picker and click it
    if not uploaded:
        try:
            print("🔍 Looking for oj-file-picker element...")
            picker = page.locator("oj-file-picker").first
            picker.wait_for(timeout=5000, state="visible")
            
            with page.expect_file_chooser(timeout=5000) as fc_info:
                picker.click()
            
            file_chooser = fc_info.value
            file_chooser.set_files(pdf_path)
            print(f"✅ Uploaded via oj-file-picker click")
            uploaded = True
            page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ oj-file-picker method failed: {e}")

    # Method 3: Pierce Shadow DOM directly
    if not uploaded:
        try:
            print("🔍 Attempting shadow DOM pierce...")
            shadow_selectors = [
                "oj-file-picker >> input[type='file']",
                "oj-file-picker >>> input[type='file']",
            ]
            
            for sel in shadow_selectors:
                try:
                    page.locator(sel).set_input_files(pdf_path)
                    print(f"✅ Uploaded via shadow selector: {sel}")
                    uploaded = True
                    break
                except:
                    continue
        except Exception as e:
            print(f"❌ Shadow DOM pierce failed: {e}")

    if not uploaded:
        print("❌ All upload methods failed.")
        page.screenshot(path="upload_error.png")
        print("📸 Screenshot saved. Please upload manually.")
        input("Press ENTER after uploading the file...")
    else:
        print(f"✅ PDF uploaded: {os.path.basename(pdf_path)}")

    # === STEP 5: Click Submit Button ===
    print("\n📤 STEP 5: Clicking Submit button...")
    try:
        # Wait for submit button to appear and be clickable
        #Find submit button and clicks
        submit_selector = '#oj-button-submit_oj6\\|text'
        page.wait_for_selector(submit_selector, timeout=10000, state="visible")
        print("✅ Submit button found")
        
        # Wait a moment to ensure everything is ready
        page.wait_for_timeout(1000)
        
        # Click the submit button
        try:
            #Falls back to js click if normal click fails
            page.click(submit_selector)
            print("✅ Submit button clicked via selector")
        except:
            # Fallback: JavaScript click
            page.evaluate("""
                () => {
                    const submitBtn = document.querySelector('#oj-button-submit_oj6\\\\|text');
                    if (submitBtn) {
                        // Click the parent button element
                        const parentBtn = submitBtn.closest('button') || submitBtn.closest('oj-button');
                        if (parentBtn) {
                            parentBtn.click();
                        } else {
                            submitBtn.click();
                        }
                    }
                }
            """)
            print("✅ Submit button clicked via JavaScript")
        
        # Wait for potential confirmation dialogs
        print("⏳ Waiting for potential confirmation dialogs...")
        page.wait_for_timeout(2000)
        
    except Exception as e:
        print(f"❌ Error clicking Submit button: {e}")
        page.screenshot(path="submit_error.png")
        print("📸 Screenshot saved.")
        input("Click Submit manually, then press ENTER...")

    # === STEP 6: Handle Confirmation Dialogs (if any) ===
    print("\n✔️ STEP 6: Checking for confirmation dialogs...")
    
    #Check if any pop ups apears (like dublicate Ajeer ID)
    def click_confirmation_button(button_id, dialog_name):
        """Helper function to click confirmation button"""
        try:
            page.wait_for_selector(f'#{button_id}', timeout=3000, state="visible")
            print(f"⚠️ {dialog_name} dialog detected")
            
            # Click OK button
            #Click OK to confirm
            try:
                page.click(f'#{button_id}')
                print(f"✅ Clicked OK on {dialog_name} dialog")
            except:
                # Fallback: JavaScript click
                page.evaluate(f"""
                    () => {{
                        const okBtn = document.querySelector('#{button_id}');
                        if (okBtn) {{
                            const innerBtn = okBtn.querySelector('button');
                            if (innerBtn) {{
                                innerBtn.click();
                            }} else {{
                                okBtn.click();
                            }}
                        }}
                    }}
                """)
                print(f"✅ Clicked OK on {dialog_name} dialog via JavaScript")
            
            page.wait_for_timeout(2000)
            return True
        except:
            return False
    
    # Check for Ajeer ID confirmation dialog
    ajeer_id_dialog = click_confirmation_button('confirmSubmitIDBtn', 'Ajeer ID duplicate')
    
    # Check for Dates confirmation dialog (might appear after first one)
    dates_dialog = click_confirmation_button('confirmSubmitDatesBtn', 'Dates overlap')
    
    if ajeer_id_dialog or dates_dialog:
        if ajeer_id_dialog and dates_dialog:
            print("✅ Both confirmation dialogs handled (Ajeer ID + Dates)")
        elif ajeer_id_dialog:
            print("✅ Ajeer ID confirmation dialog handled")
        elif dates_dialog:
            print("✅ Dates confirmation dialog handled")
    else:
        print("ℹ️ No confirmation dialogs appeared (new document submission)")
    
    print("✅ Form submitted successfully!")

    # Close page automatically for batch processing
    print(f"✅ Completed processing for {employee_id}")
    page.wait_for_timeout(1000)
    page.close()


def main():
    print("🚀 Starting automation...")
    #List all PDFs in folder
    pdf_files = [f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print(f"No PDF files found in '{PDF_FOLDER}' folder.")
        return

    #Launches Chromium browser with persistent login
    with sync_playwright() as p:
        print("🧠 Launching browser (persistent login enabled)...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=HEADLESS,
            slow_mo=300 #Slows actions by 300ms for stability
        )

        #Extracts employee ID form filename
        #Extracts data from PDF
        #Fills web from and submits
        for pdf_name in pdf_files:
            try:
                pdf_path = os.path.join(PDF_FOLDER, pdf_name)
                employee_id = os.path.splitext(pdf_name)[0]
                ajeer_id, issue_date, expiry_date = extract_pdf_data(pdf_path)
                fill_web_form(context, employee_id, ajeer_id, issue_date, expiry_date, pdf_path)
            except Exception as e:
                print(f"❌ Error with {pdf_name}: {e}")

        print("✅ All PDFs processed.")
        input("Press ENTER to close the browser...")
        context.close()

#Standard Python entry
if __name__ == "__main__":
    main()
