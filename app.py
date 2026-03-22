import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import urllib.parse
import os
import gspread
from google.oauth2.service_account import Credentials

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

# --- SIDEBAR NAVIGATION ---
st.sidebar.title("🏍️ Shree Gurudev Auto")
menu = st.sidebar.radio("Navigation", ["🔔 Reminders Dashboard", "⚙️ Manage Vehicles", "📋 Garage Database"])

# ==========================================
# 1. REMINDERS DASHBOARD
# ==========================================
if menu == "🔔 Reminders Dashboard":
    st.title("🔔 Smart Reminders Dashboard")
    st.write("Customers whose specific vehicles need attention today. (Syncing Live from Google Sheets ☁️)")

    st.sidebar.markdown("---")
    st.sidebar.subheader("📸 Promo Flyer")
    st.sidebar.write("1. Right-click the image below & click 'Copy Image'.\n2. Click 'Send WhatsApp'.\n3. Press Ctrl+V (Paste) in the chat!")
    
    if os.path.exists("flyer.png"):
        st.sidebar.image("flyer.png", use_column_width=True)
    
    df = get_all_data()
    
    if not df.empty and 'Number_Plate' in df.columns:
        SERVICE_INTERVAL_KM = 3000
        COOLDOWN_DAYS = 7 
        today = date.today()
        
        service_due_list = []
        insurance_due_list = []
        
        for index, row in df.iterrows():
            if pd.isna(row['Number_Plate']) or str(row['Number_Plate']).strip() == "":
                continue

            if pd.notna(row['Last_Reminder_Date']):
                try:
                    last_rem = datetime.strptime(str(row['Last_Reminder_Date']), '%Y-%m-%d').date()
                    if (today - last_rem).days < COOLDOWN_DAYS:
                        continue 
                except:
                    pass

            # --- PREDICTIVE KM LOGIC ---
            try:
                last_update_date = datetime.strptime(str(row['Last_Update_Date']), '%Y-%m-%d').date()
            except:
                last_update_date = today

            avg_km = int(row['Avg_KM']) if pd.notna(row['Avg_KM']) else 20
            curr_km = int(row['Current_KM']) if pd.notna(row['Current_KM']) else 0
            last_srv_km = int(row['Last_Service_KM']) if pd.notna(row['Last_Service_KM']) else 0

            days_passed = (today - last_update_date).days
            estimated_current_km = curr_km + (days_passed * avg_km)
            km_diff = estimated_current_km - last_srv_km
            
            if km_diff >= SERVICE_INTERVAL_KM:
                row['Estimated_Current_KM'] = estimated_current_km
                row['Estimated_Diff'] = km_diff
                service_due_list.append(row)
                
            # --- INSURANCE LOGIC (Ignores if blank) ---
            if pd.notna(row['Insurance_Expiry']) and str(row['Insurance_Expiry']).strip() != "":
                try:
                    exp_date = datetime.strptime(str(row['Insurance_Expiry']), '%Y-%m-%d').date()
                    if (today - timedelta(days=30)) <= exp_date <= (today + timedelta(days=15)):
                        insurance_due_list.append(row)
                except:
                    pass

        col1, col2 = st.columns(2)
        
        # --- SERVICE UI ---
        with col1:
            st.subheader("🛠️ Service Reminders")
            if service_due_list:
                for row in service_due_list:
                    msg = f"Hi {row['Customer_Name']}\n\nYour {row['Bike_Model']} ({row['Number_Plate']}) is due for service.\n\nYour last service was at {row['Last_Service_KM']} KM. Based on average usage, your bike is currently around {int(row['Estimated_Current_KM'])} KM.\n\nVisit *Shree Gurudev Automobile Services* today!\nShop no. 9, MK College Road, Kalyan(w)\nCall: +91 9323962011"
                    wa_link = generate_wa_link(str(row['Phone']), msg)
                    
                    with st.container():
                        st.markdown(f"**{row['Customer_Name']}** | {row['Bike_Model']} ({row['Number_Plate']})")
                        st.caption(f"Last Service: **{row['Last_Service_KM']} KM** | Est. Current: **{int(row['Estimated_Current_KM'])} KM**")
                        
                        c1, c2 = st.columns([2, 1])
                        with c1:
                            st.markdown(f"[📲 Send WhatsApp]({wa_link})", unsafe_allow_html=True)
                        with c2:
                            if st.button("✔️ Mark Sent", key=f"srv_{row['Number_Plate']}"):
                                update_last_reminder(row['Number_Plate'])
                                st.rerun()
                        st.divider()
            else:
                st.info("No services due.")
                
        # --- INSURANCE UI ---
        with col2:
            st.subheader("🛡️ Insurance Renewals")
            if insurance_due_list:
                for row in insurance_due_list:
                    exp_date = datetime.strptime(str(row['Insurance_Expiry']), '%Y-%m-%d').date()
                    
                    if exp_date < today:
                        msg = f"Hi {row['Customer_Name']}\n\nURGENT: The insurance for your {row['Bike_Model']} ({row['Number_Plate']}) expired on {row['Insurance_Expiry']}. Please renew immediately to avoid heavy fines!\n\nNeed help? Contact *Shree Gurudev Automobile Services* at 9323962011."
                        status_text = f"🚨 Expired on {row['Insurance_Expiry']}"
                    else:
                        msg = f"Hi {row['Customer_Name']}\n\nThe insurance for your {row['Bike_Model']} ({row['Number_Plate']}) expires on {row['Insurance_Expiry']}. Please renew it to avoid fines!\n\nNeed help? Contact *Shree Gurudev Automobile Services* at 9323962011."
                        status_text = f"⏳ Expires on {row['Insurance_Expiry']}"

                    wa_link = generate_wa_link(str(row['Phone']), msg)
                    
                    with st.container():
                        st.markdown(f"**{row['Customer_Name']}** | {row['Bike_Model']} ({row['Number_Plate']})")
                        st.caption(status_text)
                        
                        c1, c2 = st.columns([2, 1])
                        with c1:
                            st.markdown(f"[📲 Send WhatsApp]({wa_link})", unsafe_allow_html=True)
                        with c2:
                            if st.button("✔️ Mark Sent", key=f"ins_{row['Number_Plate']}"):
                                update_last_reminder(row['Number_Plate'])
                                st.rerun()
                        st.divider()
            else:
                st.info("No insurances expiring soon.")
    else:
        st.warning("No vehicles added to the database yet. Add a vehicle first!")

# ==========================================
# 2. MANAGE VEHICLES
# ==========================================
elif menu == "⚙️ Manage Vehicles":
    st.title("⚙️ Manage Vehicles")
    
    tab_add, tab_update, tab_delete = st.tabs(["➕ Add New Vehicle", "✏️ Update Existing Vehicle", "🗑️ Delete Vehicle"])
    
    with tab_add:
        st.write("Register a completely new vehicle directly to Google Sheets.")
        with st.form("add_data_form"):
            st.subheader("👤 Customer Details")
            col1, col2 = st.columns(2)
            with col1:
                phone = st.text_input("WhatsApp Number", placeholder="10 Digits Only (e.g. 9876543210)")
            with col2:
                name = st.text_input("Customer Name")
                
            st.subheader("🏍️ Vehicle Details")
            col3, col4 = st.columns(2)
            with col3:
                reg_no = st.text_input("Number Plate", placeholder="MH05AB1234")
                bike = st.text_input("Bike Model", placeholder="e.g. Honda Activa")
                ins_exp = st.date_input("Insurance Expiry Date (Leave blank if unknown)", value=None, key="add_ins")
            with col4:
                last_km = st.number_input("Last Service KM", min_value=0, step=500, key="add_last_km")
                curr_km = st.number_input("Current KM (Latest Reading)", min_value=0, step=500, key="add_curr_km")
                avg_km = st.number_input("Average KM Driven per Day", min_value=1, value=20, step=5)
                
            submit_add = st.form_submit_button("Save to Cloud Database")
            
            if submit_add:
                phone_clean = phone.replace(" ", "").replace("+91", "").strip()
                clean_reg_no = reg_no.upper().replace(" ", "")
                
                if not phone_clean.isdigit() or len(phone_clean) != 10:
                    st.error("⚠️ Invalid WhatsApp Number! Please enter exactly 10 digits.")
                elif clean_reg_no and bike and name:
                    df_check = get_all_data()
                    existing_plates = []
                    if not df_check.empty and 'Number_Plate' in df_check.columns:
                        existing_plates = df_check['Number_Plate'].astype(str).str.upper().str.replace(" ", "").tolist()
                    
                    if clean_reg_no in existing_plates:
                        st.error(f"⚠️ Number Plate {clean_reg_no} already exists! Please use the 'Update' tab.")
                    else:
                        final_ins_date = str(ins_exp) if ins_exp else ""
                        new_row = [
                            name, 
                            phone_clean, 
                            clean_reg_no, 
                            bike, 
                            last_km, 
                            curr_km, 
                            avg_km, 
                            str(date.today()), 
                            final_ins_date, 
                            ""
                        ]
                        # value_input_option="USER_ENTERED" fixes the strict Date validation bug!
                        worksheet.append_row(new_row, value_input_option="USER_ENTERED")
                        st.success(f"✅ Successfully registered {clean_reg_no} to Google Sheets!")
                else:
                    st.error("Name, Phone, Number Plate, and Bike Model are mandatory.")

    with tab_update:
        st.write("Update details for an existing vehicle. You can also replace 'TEMP' plates with real ones here!")
        df_vehicles = get_all_data()
        
        if not df_vehicles.empty and 'Number_Plate' in df_vehicles.columns:
            df_valid_vehicles = df_vehicles.dropna(subset=['Number_Plate'])
            plate_list = [p for p in df_valid_vehicles['Number_Plate'].tolist() if str(p).strip() != ""]
            
            if plate_list:
                selected_plate = st.selectbox("🔍 Search by Number Plate (or Phone/Name) to Update", plate_list, key="update_dropdown")
                vehicle_data = df_vehicles[df_vehicles['Number_Plate'] == selected_plate].iloc[0]
                
                st.info(f"👤 **Owner:** {vehicle_data['Customer_Name']} ({vehicle_data['Phone']}) | 🏍️ **Bike:** {vehicle_data['Bike_Model']}")
                
                with st.form("update_data_form"):
                    st.write("*(Change the Number Plate below if this is a TEMP plate!)*")
                    new_reg_no = st.text_input("Number Plate", value=vehicle_data['Number_Plate'])
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        safe_last_km = int(vehicle_data['Last_Service_KM']) if pd.notna(vehicle_data['Last_Service_KM']) and str(vehicle_data['Last_Service_KM']).strip() != "" else 0
                        safe_curr_km = int(vehicle_data['Current_KM']) if pd.notna(vehicle_data['Current_KM']) and str(vehicle_data['Current_KM']).strip() != "" else 0
                        new_last_km = st.number_input("Last Service KM", value=safe_last_km, step=500)
                        new_curr_km = st.number_input("Current KM (Latest Reading)", value=safe_curr_km, step=500)
                    with col2:
                        safe_avg_km = int(vehicle_data['Avg_KM']) if pd.notna(vehicle_data['Avg_KM']) and str(vehicle_data['Avg_KM']).strip() != "" else 20
                        new_avg_km = st.number_input("Average KM Driven per Day", min_value=1, value=safe_avg_km, step=5)
                        
                        try:
                            default_date = datetime.strptime(str(vehicle_data['Insurance_Expiry']), '%Y-%m-%d').date()
                        except:
                            default_date = None
                        new_ins_exp = st.date_input("Update Insurance Expiry (Leave blank if unknown)", value=default_date)
                    
                    if st.form_submit_button("Update Vehicle Details"):
                        try:
                            cell = worksheet.find(selected_plate)
                        except Exception:
                            cell = None
                            
                        if cell is not None:
                            row_idx = cell.row
                            final_ins_date = str(new_ins_exp) if new_ins_exp else ""
                            final_reg = new_reg_no.upper().replace(" ", "")
                            
                            worksheet.update_cell(row_idx, 3, final_reg)
                            worksheet.update_cell(row_idx, 5, new_last_km)
                            worksheet.update_cell(row_idx, 6, new_curr_km)
                            worksheet.update_cell(row_idx, 7, new_avg_km)
                            worksheet.update_cell(row_idx, 8, str(date.today()))
                            worksheet.update_cell(row_idx, 9, final_ins_date)
                            
                            st.success("✅ Successfully updated details in Google Sheets!")
                            st.rerun() 
                        else:
                            st.error("Error finding vehicle in database.")
            else:
                st.warning("No valid vehicles found in the database.")
        else:
            st.warning("No vehicles in the database yet. Go to the Add tab first!")

    with tab_delete:
        st.write("🗑️ Remove a vehicle permanently from the database.")
        df_vehicles = get_all_data()
        
        if not df_vehicles.empty and 'Number_Plate' in df_vehicles.columns:
            df_valid_vehicles = df_vehicles.dropna(subset=['Number_Plate'])
            plate_list = [p for p in df_valid_vehicles['Number_Plate'].tolist() if str(p).strip() != ""]
            
            if plate_list:
                del_plate = st.selectbox("🔍 Search & Select Number Plate to DELETE", plate_list, key="delete_dropdown")
                vehicle_data = df_vehicles[df_vehicles['Number_Plate'] == del_plate].iloc[0]
                
                st.error(f"⚠️ You are about to permanently delete **{del_plate}** ({vehicle_data['Bike_Model']}) owned by **{vehicle_data['Customer_Name']}**.")
                st.write("This action cannot be undone.")
                
                if st.button(f"🚨 Yes, Delete {del_plate} forever"):
                    try:
                        cell = worksheet.find(del_plate)
                    except Exception:
                        cell = None
                        
                    if cell is not None:
                        worksheet.delete_rows(cell.row)
                        st.success(f"✅ Vehicle {del_plate} has been deleted.")
                        st.rerun()
                    else:
                        st.error("⚠️ Error finding vehicle to delete. It may have already been removed.")
        else:
            st.info("No vehicles available to delete.")

# ==========================================
# 3. DATABASE VIEW & CSV IMPORT
# ==========================================
elif menu == "📋 Garage Database":
    st.title("📋 Live Google Sheets Database")
    st.markdown("[🔗 Click here to open your Google Sheet directly in your browser](https://docs.google.com/spreadsheets/)", unsafe_allow_html=True)
    
    df_vehicles = get_all_data()
    
    # --- CLOUD CSV UPLOADER ---
    with st.expander("📥 Import Old Customers from CSV"):
        st.write("Upload your old customer CSV file below to push them into your Google Sheet.")
        
        uploaded_file = st.file_uploader("Choose your CSV file", type=['csv'])
        
        if uploaded_file is not None:
            if st.button("🚀 Run One-Time Import"):
                try:
                    df_csv = pd.read_csv(uploaded_file)
                    
                    existing_plates = []
                    if not df_vehicles.empty and 'Number_Plate' in df_vehicles.columns:
                        existing_plates = df_vehicles['Number_Plate'].astype(str).str.upper().tolist()
                    
                    rows_to_add = []
                    for index, row in df_csv.iterrows():
                        raw_phone = str(row.get('Phone', ''))
                        csv_phone = raw_phone.replace('.0', '').replace(' ', '').replace('+91', '').strip()
                        
                        if len(csv_phone) > 10:
                            csv_phone = csv_phone[-10:]
                        
                        if len(csv_phone) == 10 and csv_phone.isdigit():
                            # The Bulletproof Primary Key logic (Phone Number + Row Index)
                            temp_plate = f"TEMP-{csv_phone}-{index}"
                            
                            if temp_plate not in existing_plates:
                                bike_model = str(row.get('Bike_Model', '')) if pd.notna(row.get('Bike_Model')) else ""
                                name = str(row.get('Name', 'Unknown Customer'))
                                
                                rows_to_add.append([name, csv_phone, temp_plate, bike_model, 0, 0, 20, str(date.today()), "", ""])
                    
                    if rows_to_add:
                        worksheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")
                        st.success(f"✅ Successfully imported {len(rows_to_add)} valid customers to Google Sheets!")
                        st.rerun()
                    else:
                        st.info("⚠️ No new customers to add. (They might already be imported, or the phone numbers in the CSV are invalid).")
                except Exception as e:
                    st.error(f"Error during import: {e}")
    
    st.divider()

    if not df_vehicles.empty:
        st.write(f"Total Entries Registered: **{len(df_vehicles)}**")
        search = st.text_input("🔍 Search Vehicles by Number Plate, Name, or Phone")
        if search:
            df_vehicles = df_vehicles[
                df_vehicles.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)
            ]
        st.dataframe(df_vehicles, use_container_width=True)
    else:
        st.info("No vehicles registered yet. The Google Sheet is empty!")
