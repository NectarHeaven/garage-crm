import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import urllib.parse
import os
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

st.set_page_config(page_title="Smart Garage CRM", page_icon="🏍️", layout="wide")

# --- CLOUD SECURE GOOGLE SHEETS SETUP ---
try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    gc = gspread.authorize(credentials)
    
    sh = gc.open("Smart Garage CRM")
    worksheet = sh.worksheet("Database")
except Exception as e:
    st.error(f"⚠️ Could not connect to Google Sheets. Check your Streamlit Secrets! Error: {e}")
    st.stop()

# --- AI MESSAGE GENERATOR (PROFESSIONAL & CULTURALLY NEUTRAL) ---
@st.cache_data(ttl=3600, show_spinner=False)
def draft_ai_message(name, bike, context):
    try:
        if "gemini_api_key" not in st.secrets:
            return None 
        
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        Write a short, highly professional WhatsApp message (max 3 sentences) in a mix of Marathi and English. 
        Customer Name field: '{name}'
        Bike: '{bike}'
        Reason for message: '{context}'
        
        CRITICAL RULES:
        1. Use a universally professional English greeting. If a full name is provided, extract the title and surname (e.g., 'Dear Mr. Sharma' or 'Dear Ms. Patil').
        2. If the name field is just 'MRS', 'Unknown Customer', a single letter, or looks incomplete, strictly use 'Dear Customer,'.
        3. NEVER use religious or culturally specific greetings (like Namaste, Ram Ram, etc.).
        4. Keep it purely business. Do not add any festival wishes.
        5. End with '- Shree Gurudev Automobile Services'.
        """
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return None 

def get_all_data():
    records = worksheet.get_all_records()
    df = pd.DataFrame(records)
    if not df.empty:
        df.replace("", pd.NA, inplace=True)
    return df

def generate_wa_link(phone, message):
    encoded_msg = urllib.parse.quote(message)
    clean_phone = str(phone).replace(".0", "").replace(" ", "").strip()
    if len(clean_phone) == 10 and clean_phone.isdigit():
        clean_phone = f"91{clean_phone}"
    return f"https://wa.me/{clean_phone}?text={encoded_msg}"

def update_last_reminder(reg_no):
    try:
        cell = worksheet.find(reg_no)
        if cell:
            worksheet.update_cell(cell.row, 10, str(date.today()))
    except Exception:
        pass

def clear_pending_part(reg_no):
    try:
        cell = worksheet.find(reg_no)
        if cell:
            worksheet.update_cell(cell.row, 12, "")
    except Exception:
        pass

# --- SIDEBAR NAVIGATION ---
st.sidebar.title("🏍️ Shree Gurudev Auto")
menu = st.sidebar.radio("Navigation", ["🔔 Reminders Dashboard", "⚙️ Manage Vehicles", "📋 Garage Database"])

# ==========================================
# 1. REMINDERS DASHBOARD
# ==========================================
if menu == "🔔 Reminders Dashboard":
    st.title("🔔 Smart Reminders Dashboard")
    st.write("Customers whose specific vehicles need attention today.")
    
    df = get_all_data()
    
    if not df.empty and 'Number_Plate' in df.columns:
        SERVICE_INTERVAL_KM = 1800  # Updated to 1800 KM
        COOLDOWN_DAYS = 7 
        today = date.today()
        
        service_due_list = []
        insurance_due_list = []
        puc_due_list = []
        pending_parts_list = []
        
        for index, row in df.iterrows():
            if pd.isna(row.get('Number_Plate')) or str(row.get('Number_Plate')).strip() == "":
                continue

            skip_service_alert = False
            if pd.notna(row.get('Last_Reminder_Date')):
                try:
                    last_rem = datetime.strptime(str(row['Last_Reminder_Date']), '%Y-%m-%d').date()
                    if (today - last_rem).days < COOLDOWN_DAYS:
                        skip_service_alert = True 
                except:
                    pass

            # --- PREDICTIVE KM LOGIC (Service) ---
            if not skip_service_alert:
                try: last_update_date = datetime.strptime(str(row.get('Last_Update_Date', today)), '%Y-%m-%d').date()
                except: last_update_date = today

                avg_km = int(row['Avg_KM']) if pd.notna(row.get('Avg_KM')) else 20
                curr_km = int(row['Current_KM']) if pd.notna(row.get('Current_KM')) else 0
                last_srv_km = int(row['Last_Service_KM']) if pd.notna(row.get('Last_Service_KM')) else 0

                days_passed = (today - last_update_date).days
                estimated_current_km = curr_km + (days_passed * avg_km)
                km_diff = estimated_current_km - last_srv_km
                
                if km_diff >= SERVICE_INTERVAL_KM:
                    row['Estimated_Current_KM'] = estimated_current_km
                    service_due_list.append(row)
                
            # --- INSURANCE LOGIC (+/- 15 Days) ---
            if pd.notna(row.get('Insurance_Expiry')) and str(row.get('Insurance_Expiry')).strip() != "":
                try:
                    exp_date = datetime.strptime(str(row['Insurance_Expiry']), '%Y-%m-%d').date()
                    if (today - timedelta(days=15)) <= exp_date <= (today + timedelta(days=15)):
                        row['Ins_Status'] = "Expired" if exp_date < today else "Expiring Soon"
                        insurance_due_list.append(row)
                except:
                    pass

            # --- PUC LOGIC ---
            if pd.notna(row.get('PUC_Expiry')) and str(row.get('PUC_Expiry')).strip() != "":
                try:
                    puc_exp_date = datetime.strptime(str(row['PUC_Expiry']), '%Y-%m-%d').date()
                    if (today - timedelta(days=15)) <= puc_exp_date <= (today + timedelta(days=7)):
                        row['PUC_Status'] = "Expired" if puc_exp_date < today else "Expiring Soon"
                        puc_due_list.append(row)
                except:
                    pass

            # --- PENDING PARTS LOGIC ---
            if pd.notna(row.get('Pending_Parts')) and str(row.get('Pending_Parts')).strip() != "":
                pending_parts_list.append(row)

        # ---------------- UI DASHBOARD RENDER ----------------
        tab_srv, tab_ins, tab_puc, tab_parts = st.tabs([
            f"🛠️ Services ({len(service_due_list)})", 
            f"🛡️ Insurance ({len(insurance_due_list)})", 
            f"💨 PUC ({len(puc_due_list)})", 
            f"📦 Pending Parts ({len(pending_parts_list)})"
        ])
        
        # 1. SERVICES
        with tab_srv:
            if service_due_list:
                for row in service_due_list:
                    context = f"Their bike has reached an estimated {int(row['Estimated_Current_KM'])} KM. It is time for their routine servicing."
                    
                    msg_key = f"srv_msg_{row['Number_Plate']}"
                    if msg_key not in st.session_state:
                        ai_msg = draft_ai_message(row['Customer_Name'], row['Bike_Model'], context)
                        default_msg = f"Dear Customer,\n\nYour {row['Bike_Model']} is due for service. Visit Shree Gurudev Automobile Services today!\nShop no. 9, MK College Road, Kalyan(w)"
                        st.session_state[msg_key] = ai_msg if ai_msg else default_msg
                    
                    with st.container():
                        st.markdown(f"**{row['Customer_Name']}** | {row['Bike_Model']} ({row['Number_Plate']})")
                        st.caption(f"Last Service: **{row['Last_Service_KM']} KM** | Est. Current: **{int(row['Estimated_Current_KM'])} KM**")
                        
                        # EDITABLE TEXT BOX
                        edited_msg = st.text_area("✍️ Review/Edit Message before sending:", value=st.session_state[msg_key], key=f"edit_{msg_key}", height=120)
                        wa_link = generate_wa_link(str(row['Phone']), edited_msg)
                        
                        c1, c2 = st.columns([2, 1])
                        with c1: st.markdown(f"[📲 Send WhatsApp]({wa_link})", unsafe_allow_html=True)
                        with c2:
                            if st.button("✔️ Mark Sent", key=f"btn_srv_{row['Number_Plate']}"):
                                update_last_reminder(row['Number_Plate'])
                                st.rerun()
                        st.divider()
            else:
                st.info("No services due.")

        # 2. INSURANCE
        with tab_ins:
            if insurance_due_list:
                for row in insurance_due_list:
                    context = f"Their bike insurance expires on {row['Insurance_Expiry']}. Remind them to renew it to avoid RTO fines."
                    
                    msg_key = f"ins_msg_{row['Number_Plate']}"
                    if msg_key not in st.session_state:
                        ai_msg = draft_ai_message(row['Customer_Name'], row['Bike_Model'], context)
                        default_msg = f"Dear Customer,\n\nThe insurance for your {row['Bike_Model']} expires on {row['Insurance_Expiry']}. Please renew it to avoid fines!\n\n- Shree Gurudev Auto"
                        st.session_state[msg_key] = ai_msg if ai_msg else default_msg
                    
                    with st.container():
                        st.markdown(f"**{row['Customer_Name']}** | {row['Bike_Model']} ({row['Number_Plate']})")
                        st.caption(f"Status: **{row['Ins_Status']}** ({row['Insurance_Expiry']})")
                        
                        edited_msg = st.text_area("✍️ Review/Edit Message:", value=st.session_state[msg_key], key=f"edit_{msg_key}", height=120)
                        wa_link = generate_wa_link(str(row['Phone']), edited_msg)
                        
                        c1, c2 = st.columns([2, 1])
                        with c1: st.markdown(f"[📲 Send WhatsApp]({wa_link})", unsafe_allow_html=True)
                        with c2:
                            if st.button("✔️ Mark Sent", key=f"btn_ins_{row['Number_Plate']}"):
                                update_last_reminder(row['Number_Plate'])
                                st.rerun()
                        st.divider()
            else:
                st.info("No insurances expiring soon.")

        # 3. PUC
        with tab_puc:
            if puc_due_list:
                for row in puc_due_list:
                    context = f"Their bike PUC (Pollution Under Control) certificate expires on {row['PUC_Expiry']}. Remind them to get it checked."
                    
                    msg_key = f"puc_msg_{row['Number_Plate']}"
                    if msg_key not in st.session_state:
                        ai_msg = draft_ai_message(row['Customer_Name'], row['Bike_Model'], context)
                        default_msg = f"Dear Customer, the PUC for your {row['Bike_Model']} expires on {row['PUC_Expiry']}. Please renew it! - Shree Gurudev Auto"
                        st.session_state[msg_key] = ai_msg if ai_msg else default_msg
                    
                    with st.container():
                        st.markdown(f"**{row['Customer_Name']}** | {row['Bike_Model']} ({row['Number_Plate']})")
                        st.caption(f"Status: **{row['PUC_Status']}** ({row['PUC_Expiry']})")
                        
                        edited_msg = st.text_area("✍️ Review/Edit Message:", value=st.session_state[msg_key], key=f"edit_{msg_key}", height=100)
                        wa_link = generate_wa_link(str(row['Phone']), edited_msg)
                        
                        c1, c2 = st.columns([2, 1])
                        with c1: st.markdown(f"[📲 Send WhatsApp]({wa_link})", unsafe_allow_html=True)
                        with c2:
                            if st.button("✔️ Mark Sent", key=f"btn_puc_{row['Number_Plate']}"):
                                update_last_reminder(row['Number_Plate'])
                                st.rerun()
                        st.divider()
            else:
                st.info("No PUC renewals due.")

        # 4. PENDING PARTS
        with tab_parts:
            if pending_parts_list:
                for row in pending_parts_list:
                    part_name = str(row['Pending_Parts'])
                    context = f"They ordered a '{part_name}' for their bike. Let them know the part has arrived at the garage and they can visit to get it fitted."
                    
                    msg_key = f"prt_msg_{row['Number_Plate']}"
                    if msg_key not in st.session_state:
                        ai_msg = draft_ai_message(row['Customer_Name'], row['Bike_Model'], context)
                        default_msg = f"Dear Customer, good news! The part ({part_name}) you requested for your {row['Bike_Model']} has arrived at Shree Gurudev Auto. Come by anytime!"
                        st.session_state[msg_key] = ai_msg if ai_msg else default_msg
                    
                    with st.container():
                        st.markdown(f"**{row['Customer_Name']}** | {row['Bike_Model']} ({row['Number_Plate']})")
                        st.error(f"📦 Waiting for: **{part_name}**")
                        
                        edited_msg = st.text_area("✍️ Review/Edit Message:", value=st.session_state[msg_key], key=f"edit_{msg_key}", height=100)
                        wa_link = generate_wa_link(str(row['Phone']), edited_msg)
                        
                        c1, c2 = st.columns([2, 1])
                        with c1: st.markdown(f"[📲 Send WhatsApp]({wa_link})", unsafe_allow_html=True)
                        with c2:
                            if st.button("✔️ Part Installed (Clear)", key=f"btn_prt_{row['Number_Plate']}"):
                                clear_pending_part(row['Number_Plate'])
                                st.rerun()
                        st.divider()
            else:
                st.info("No customers are currently waiting for parts.")

    else:
        st.warning("No vehicles added to the database yet. Add a vehicle first!")

# ==========================================
# 2. MANAGE VEHICLES
# ==========================================
elif menu == "⚙️ Manage Vehicles":
    st.title("⚙️ Manage Vehicles")
    
    tab_add, tab_update, tab_delete = st.tabs(["➕ Add New Vehicle", "✏️ Update Existing Vehicle", "🗑️ Delete Vehicle"])
    
    # --- ADD NEW VEHICLE ---
    with tab_add:
        with st.form("add_data_form"):
            col1, col2 = st.columns(2)
            with col1:
                phone = st.text_input("WhatsApp Number", placeholder="10 Digits Only")
                reg_no = st.text_input("Number Plate", placeholder="MH05AB1234")
                last_km = st.number_input("Last Service KM", min_value=0, step=500)
                ins_exp = st.date_input("Insurance Expiry Date (Optional)", value=None)
                pending_part = st.text_input("Parts Ordered / Pending (Optional)", placeholder="e.g. Rear Shock Absorber")
            with col2:
                name = st.text_input("Customer Name")
                bike = st.text_input("Bike Model", placeholder="e.g. Honda Activa")
                curr_km = st.number_input("Current KM (Latest Reading)", min_value=0, step=500)
                avg_km = st.number_input("Average KM Driven per Day", min_value=1, value=20, step=5)
                puc_exp = st.date_input("PUC Expiry Date (Optional)", value=None)
                
            submit_add = st.form_submit_button("Save to Cloud Database")
            
            if submit_add:
                phone_clean = phone.replace(" ", "").replace("+91", "").strip()
                clean_reg_no = reg_no.upper().replace(" ", "")
                
                if not phone_clean.isdigit() or len(phone_clean) != 10:
                    st.error("⚠️ Invalid WhatsApp Number!")
                elif clean_reg_no and bike and name:
                    df_check = get_all_data()
                    existing_plates = []
                    if not df_check.empty and 'Number_Plate' in df_check.columns:
                        existing_plates = df_check['Number_Plate'].astype(str).str.upper().str.replace(" ", "").tolist()
                    
                    if clean_reg_no in existing_plates:
                        st.error(f"⚠️ Number Plate {clean_reg_no} already exists! Please use the 'Update' tab.")
                    else:
                        new_row = [
                            name, phone_clean, clean_reg_no, bike, 
                            last_km, curr_km, avg_km, str(date.today()), 
                            str(ins_exp) if ins_exp else "", "", 
                            str(puc_exp) if puc_exp else "", pending_part
                        ]
                        worksheet.append_row(new_row, value_input_option="USER_ENTERED")
                        st.success(f"✅ Successfully registered {clean_reg_no}!")
                else:
                    st.error("Name, Phone, Number Plate, and Bike Model are mandatory.")

    # --- UPDATE EXISTING VEHICLE ---
    with tab_update:
        df_vehicles = get_all_data()
        
        if not df_vehicles.empty and 'Number_Plate' in df_vehicles.columns:
            df_valid_vehicles = df_vehicles.dropna(subset=['Number_Plate'])
            plate_list = [p for p in df_valid_vehicles['Number_Plate'].tolist() if str(p).strip() != ""]
            existing_plates = df_valid_vehicles['Number_Plate'].astype(str).str.upper().str.replace(" ", "").tolist()
            
            if plate_list:
                selected_plate = st.selectbox("🔍 Search by Number Plate (or Phone/Name) to Update", plate_list)
                vehicle_data = df_vehicles[df_vehicles['Number_Plate'] == selected_plate].iloc[0]
                
                with st.form("update_data_form"):
                    new_reg_no = st.text_input("Number Plate (Change if TEMP)", value=vehicle_data['Number_Plate'])
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        safe_last_km = int(vehicle_data.get('Last_Service_KM', 0)) if pd.notna(vehicle_data.get('Last_Service_KM')) and str(vehicle_data.get('Last_Service_KM')).strip() != "" else 0
                        safe_curr_km = int(vehicle_data.get('Current_KM', 0)) if pd.notna(vehicle_data.get('Current_KM')) and str(vehicle_data.get('Current_KM')).strip() != "" else 0
                        new_last_km = st.number_input("Last Service KM", value=safe_last_km, step=500)
                        new_curr_km = st.number_input("Current KM (Latest Reading)", value=safe_curr_km, step=500)
                        
                        try: default_ins = datetime.strptime(str(vehicle_data.get('Insurance_Expiry', '')), '%Y-%m-%d').date()
                        except: default_ins = None
                        new_ins_exp = st.date_input("Update Insurance Expiry", value=default_ins)
                        
                    with col2:
                        safe_avg_km = int(vehicle_data.get('Avg_KM', 20)) if pd.notna(vehicle_data.get('Avg_KM')) and str(vehicle_data.get('Avg_KM')).strip() != "" else 20
                        new_avg_km = st.number_input("Average KM Driven per Day", min_value=1, value=safe_avg_km, step=5)
                        
                        try: default_puc = datetime.strptime(str(vehicle_data.get('PUC_Expiry', '')), '%Y-%m-%d').date()
                        except: default_puc = None
                        new_puc_exp = st.date_input("Update PUC Expiry", value=default_puc)
                        
                        current_parts = str(vehicle_data.get('Pending_Parts', ''))
                        if current_parts == "<NA>" or current_parts == "nan": current_parts = ""
                        new_pending_part = st.text_input("Parts Ordered / Pending", value=current_parts)
                    
                    if st.form_submit_button("Update Vehicle Details"):
                        final_reg = new_reg_no.upper().replace(" ", "")
                        
                        if final_reg != selected_plate and final_reg in existing_plates:
                            st.error(f"⚠️ Action Blocked: The plate **{final_reg}** already belongs to someone else!")
                        else:
                            try: cell = worksheet.find(selected_plate)
                            except: cell = None
                                
                            if cell is not None:
                                row_idx = cell.row
                                worksheet.update_cell(row_idx, 3, final_reg)
                                worksheet.update_cell(row_idx, 5, new_last_km)
                                worksheet.update_cell(row_idx, 6, new_curr_km)
                                worksheet.update_cell(row_idx, 7, new_avg_km)
                                worksheet.update_cell(row_idx, 8, str(date.today()))
                                worksheet.update_cell(row_idx, 9, str(new_ins_exp) if new_ins_exp else "")
                                worksheet.update_cell(row_idx, 11, str(new_puc_exp) if new_puc_exp else "")
                                worksheet.update_cell(row_idx, 12, new_pending_part)
                                
                                st.success("✅ Successfully updated details!")
                                st.rerun() 
                            else:
                                st.error("Error finding vehicle in database.")
            else:
                st.warning("No valid vehicles found in the database.")

    # --- DELETE VEHICLE ---
    with tab_delete:
        df_vehicles = get_all_data()
        if not df_vehicles.empty and 'Number_Plate' in df_vehicles.columns:
            df_valid_vehicles = df_vehicles.dropna(subset=['Number_Plate'])
            plate_list = [p for p in df_valid_vehicles['Number_Plate'].tolist() if str(p).strip() != ""]
            
            if plate_list:
                del_plate = st.selectbox("🔍 Search & Select Number Plate to DELETE", plate_list)
                if st.button(f"🚨 Yes, Delete {del_plate} forever"):
                    try:
                        cell = worksheet.find(del_plate)
                        if cell:
                            worksheet.delete_rows(cell.row)
                            st.success(f"✅ Vehicle {del_plate} has been deleted.")
                            st.rerun()
                    except:
                        st.error("⚠️ Error finding vehicle to delete.")

# ==========================================
# 3. DATABASE VIEW
# ==========================================
elif menu == "📋 Garage Database":
    st.title("📋 Live Google Sheets Database")
    st.markdown("[🔗 Open Google Sheet](https://docs.google.com/spreadsheets/)", unsafe_allow_html=True)
    
    df_vehicles = get_all_data()
    
    with st.expander("📥 Import Old Customers from CSV"):
        uploaded_file = st.file_uploader("Choose your CSV file", type=['csv'])
        if uploaded_file is not None:
            if st.button("🚀 Run One-Time Import"):
                try:
                    df_csv = pd.read_csv(uploaded_file)
                    existing_plates = df_vehicles['Number_Plate'].astype(str).str.upper().tolist() if not df_vehicles.empty and 'Number_Plate' in df_vehicles.columns else []
                    
                    rows_to_add = []
                    for index, row in df_csv.iterrows():
                        csv_phone = str(row.get('Phone', '')).replace('.0', '').replace(' ', '').replace('+91', '').strip()[-10:]
                        if len(csv_phone) == 10 and csv_phone.isdigit():
                            temp_plate = f"TEMP-{csv_phone}-{index}"
                            if temp_plate not in existing_plates:
                                bike_model = str(row.get('Bike_Model', '')) if pd.notna(row.get('Bike_Model')) else ""
                                name = str(row.get('Name', 'Unknown Customer'))
                                rows_to_add.append([name, csv_phone, temp_plate, bike_model, 0, 0, 20, str(date.today()), "", "", "", ""])
                    
                    if rows_to_add:
                        worksheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")
                        st.success(f"✅ Successfully imported {len(rows_to_add)} valid customers!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error during import: {e}")
    
    st.divider()

    if not df_vehicles.empty:
        st.write(f"Total Entries: **{len(df_vehicles)}**")
        search = st.text_input("🔍 Search Database")
        if search:
            df_vehicles = df_vehicles[df_vehicles.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
        st.dataframe(df_vehicles, use_container_width=True)
