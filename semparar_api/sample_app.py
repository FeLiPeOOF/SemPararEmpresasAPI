import os
import xml.etree.ElementTree as ET
from semparar import SemPararEmpresasClient, SessionExpiredError, LoginError

def load_config(config_path="sample.xml"):
    """Loads login credentials and filters from XML configuration file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file {config_path} not found.")
        
    tree = ET.parse(config_path)
    root = tree.getroot()
    
    config = {}
    for elem in ["login_type", "login_value", "password", "cookies_path", "twocaptcha_api_key", "start_date", "end_date", "use_interactive_login"]:
        node = root.find(elem)
        config[elem] = node.text if node is not None and node.text is not None else ""
        
    return config

def parse_date_for_sorting(date_str):
    """Parses dd/mm/yyyy Brazilian date format into yyyy-mm-dd for string sorting."""
    try:
        parts = date_str.split("/")
        if len(parts) == 3:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
    except Exception:
        pass
    return "0000-00-00"

def main():
    # Load configuration
    config_path = "sample.xml"
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        try:
            config_path = "semparar_api/sample.xml"
            config = load_config(config_path)
        except FileNotFoundError:
            print("Could not find sample.xml. Please make sure it exists in the execution path.")
            return

    cookies_path = config["cookies_path"] or "semparar_cookies.json"
    # If the cookie file is not found at the specified path, check relative to the config directory
    if not os.path.exists(cookies_path):
        config_dir = os.path.dirname(config_path)
        if config_dir:
            alternative_path = os.path.join(config_dir, cookies_path)
            if os.path.exists(alternative_path):
                cookies_path = alternative_path

    use_interactive_login_val = config.get("use_interactive_login", "true")
    if not use_interactive_login_val:
        use_interactive_login_val = "true"
    use_interactive_login = use_interactive_login_val.strip().lower() != "false"

    print(f"Initializing Sem Parar Empresas Client (cookies path: {cookies_path}, interactive login: {use_interactive_login})...")
    client = SemPararEmpresasClient(
        login_type=config["login_type"],
        login_value=config["login_value"],
        password=config["password"],
        cookies_path=cookies_path,
        twocaptcha_api_key=config["twocaptcha_api_key"],
        use_interactive_login=use_interactive_login
    )
    
    try:
        success = client.login()
        if success:
            print("\n=========================================")
            print("Authentication Successful!")
            print("Session is active and ready to get data.")
            print("=========================================")
            
            # Fetch and print specific registration details
            try:
                print("\nFetching Account Registration Data...")
                account_data = client.get_account_data()
                
                # Look for common key variants in the parsed dictionary
                name = None
                for key in ["Nome", "Razão Social", "Nome Fantasia", "Nome da Empresa", "Razao Social", "usuario.login"]:
                    if key in account_data:
                        name = account_data[key]
                        break
                        
                email = None
                for key in ["Email", "E-mail", "UserEmail", "usuario.email"]:
                    if key in account_data:
                        email = account_data[key]
                        break
                        
                # Extract CNPJ
                cnpj = account_data.get("CnpjCpf") or account_data.get("CNPJ")
                
                # Check all phone number fields
                phones = []
                t1 = account_data.get("Telefone1")
                t2 = account_data.get("Telefone2")
                cel = account_data.get("Celular")
                
                if t1:
                    phones.append(f"{t1} (Tel 1)")
                if t2:
                    phones.append(f"{t2} (Tel 2)")
                if cel:
                    phones.append(f"{cel} (Cel)")
                    
                if phones:
                    phone_str = ", ".join(phones)
                else:
                    phone_str = None
                    for key in ["Telefone", "Celular", "Telefone Comercial", "DDD/Telefone", "usuario.telefone"]:
                        if key in account_data:
                            phone_str = account_data[key]
                            break
                
                city = account_data.get("Cidade")
                state = account_data.get("Estado")
                location = f"{city} - {state}" if city and state else None
                
                print("\n=========================================")
                print("           ACCOUNT INFO                  ")
                print("=========================================")
                print(f"  Name/Company: {name or 'Not found'}")
                if cnpj:
                    print(f"  CNPJ/CPF:     {cnpj}")
                print(f"  Email:        {email or 'Not found'}")
                print(f"  Phone:        {phone_str or 'Not found'}")
                if location:
                    print(f"  Location:     {location}")
                print("=========================================")
                
            except Exception as e:
                print(f"Failed to fetch account data: {e}")
                
            # Fetch invoices with date filters
            try:
                start_date = config.get("start_date")
                end_date = config.get("end_date")
                
                if start_date and end_date:
                    print(f"\nFetching Invoices filtered by date ({start_date} to {end_date})...")
                else:
                    print("\nFetching Invoices (No date filter applied)...")
                    
                invoices = client.get_invoices(
                    product_type="STP",
                    start_date=start_date if start_date else None,
                    end_date=end_date if end_date else None
                )
                
                print(f"Total invoices retrieved: {len(invoices)}")
                
                # Filter for closed invoices (status not "Em Aberto" and has a valid invoice number)
                closed_invoices = [inv for inv in invoices if inv.get("DescricaoSituacao") != "Em Aberto" and inv.get("Fatura")]
                
                if closed_invoices:
                    # Sort invoices by due date descending (latest first)
                    date_key = "Vencimento"
                    closed_invoices.sort(key=lambda x: parse_date_for_sorting(x.get(date_key, "")), reverse=True)
                    
                    last_closed = closed_invoices[0]
                    fatura_num = last_closed["Fatura"]
                    
                    print("\n=========================================")
                    print("         LATEST CLOSED INVOICE           ")
                    print("=========================================")
                    for k, v in last_closed.items():
                        print(f"  {k}: {v}")
                    print("=========================================")
                    
                    # Download PDF
                    try:
                        pdf_data = client.download_invoice_pdf(fatura_num)
                        pdf_filename = f"fatura_{fatura_num}.pdf"
                        with open(pdf_filename, "wb") as f:
                            f.write(pdf_data)
                        print(f"  [+] Downloaded last closed invoice PDF to: {pdf_filename} ({len(pdf_data)} bytes)")
                    except Exception as pdf_err:
                        print(f"  [-] Failed to download PDF: {pdf_err}")
                        
                    # Download Excel
                    try:
                        xls_data = client.download_invoice_xls(fatura_num)
                        if len(xls_data) > 0:
                            xls_filename = f"fatura_{fatura_num}.xlsx"
                            with open(xls_filename, "wb") as f:
                                f.write(xls_data)
                            print(f"  [+] Downloaded last closed invoice Excel to: {xls_filename} ({len(xls_data)} bytes)")
                        else:
                            print(f"  [+] Excel report generation triggered successfully and will be sent to {email or 'company email'}.")
                    except Exception as xls_err:
                        print(f"  [-] Failed to download Excel: {xls_err}")
                else:
                    print("\nNo closed invoices found matching criteria.")
            except Exception as e:
                print(f"Failed to fetch invoices: {e}")
        else:
            print("\nLogin failed without throwing an error.")
            
    except SessionExpiredError as e:
        print(f"\n[Session Expired/Missing]: {e}")
        print("Please log in via your web browser and save your cookies to semparar_cookies.json,")
        print("or fill in the <twocaptcha_api_key> tag in sample.xml for fully automatic background solving.")
        
    except LoginError as e:
        print(f"\n[Login Error]: {e}")
        
    except Exception as e:
        print(f"\n[Error]: {e}")

if __name__ == "__main__":
    main()
