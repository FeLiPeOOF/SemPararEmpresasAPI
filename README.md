# Sem Parar Empresas Client API

A robust, background-friendly Python API client to automate authentication, cadastral data extraction, and invoice downloads (PDF and Excel/XLSX) from the **Sem Parar Empresas** portal.

---

## Features

1. **Dual Authentication Strategy**:
   - **Session Cookie Cache**: Loads and persists session cookies in a local JSON file (`semparar_cookies.json`). Valid sessions bypass login entirely (100% background-friendly and fast).
   - **Background Captcha Solver (2Captcha)**: Integrates with the 2Captcha API to solve the portal's `MTCaptcha` challenge headlessly.
   - **Interactive Login Fallback**: Optionally pops up a headful Playwright browser window on session expiry for manual captcha solving, saving the session cookies once authenticated.
2. **Cadastral Company Details**: Fetches company name, CNPJ, email, physical address, and all contact phones.
3. **Invoice Grid Mapping**: Emulates the portal's Kendo MVC pagination filters to fetch the complete lists of invoices.
4. **Direct PDF & XLSX Downloads**: Downloads the official PDF invoices and detailed Excel spreadsheets for closed invoices directly as binary bytes.
5. **Open Invoice Trigger**: Safely triggers open items/uninvoiced transaction XLSX spreadsheets to be generated and emailed directly.

---

## Directory Structure

* [semparar_api/semparar.py](file:///Users/felipeneres/Documents/SemPararAPI/semparar_api/semparar.py): Main client implementation containing the `SemPararEmpresasClient` class.
* [semparar_api/sample_app.py](file:///Users/felipeneres/Documents/SemPararAPI/semparar_api/sample_app.py): Demonstrator script filtering for the latest closed invoice and downloading files.
* [semparar_api/sample.xml](file:///Users/felipeneres/Documents/SemPararAPI/semparar_api/sample.xml): Settings and credentials file.
* [test_client.py](file:///Users/felipeneres/Documents/SemPararAPI/test_client.py): Comprehensive unit tests verifying mock parsing, authentication fallbacks, and downloads.

---

## Configuration (`sample.xml`)

Provide your portal credentials, filter dates, and 2Captcha key in an XML configuration file:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
    <!-- Login type can be "CNPJ", "Email", or "Username" -->
    <login_type>Username</login_type>
    <login_value>YOUR_PORTAL_USER</login_value>
    <password>YOUR_PORTAL_PASSWORD</password>
    <cookies_path>semparar_cookies.json</cookies_path>
    
    <!-- Optional: 2Captcha API Key to solve the MTCaptcha headlessly in the background -->
    <twocaptcha_api_key>YOUR_2CAPTCHA_API_KEY</twocaptcha_api_key>
    
    <!-- Date filters in Brazilian format (dd/mm/yyyy) -->
    <start_date>01/02/2026</start_date>
    <end_date>30/06/2026</end_date>
    
    <!-- Set to "true" to open a manual browser popup on session expiry, or "false" to run headlessly -->
    <use_interactive_login>false</use_interactive_login>
</configuration>
```

---

## How it Works (Under the Hood)

### 1. Session Cache Check
The client calls `verify_session()`, which tests session validity by requesting the billing seguro subdomain `/Financeiro/Fatura/ConsultarFaturas_AbaProdutoListarTipo` with `allow_redirects=False`. If it redirects (302) to the login screen, it indicates session expiration.

### 2. Login Flow
If cookies are missing/invalid:
- **With `twocaptcha_api_key`**: The client fetches the login page CSRF token (`__RequestVerificationToken`), submits the `MTCaptcha` key `MTPublic-ABLdYsRql` to the 2Captcha solver API, waits for the solved token, and makes a POST to `/Login/Index` in the background.
- **Without `twocaptcha_api_key` but `use_interactive_login=True`**: Playwright launches a Chromium browser window, pre-fills the login form, and waits for the user to solve the captcha. Upon redirecting to the portal, cookies are extracted and stored.

### 3. Cadastral Data Extraction
Queries the server-side rendered legacy subdomain `/SemParar/DadosCliente/DadosSemParar_AbaDadosCadastrais`. BeautifulSoup parses form elements (inputs like `#Nome`, `#CnpjCpf`, `#Telefone1`, `#Telefone2`, `#Celular`, and `#Email`), returning a complete key-value dictionary.

### 4. Invoice Grid Queries
Replicates the Kendo MVC grid communication flow:
1. **Filter Update**: Sends a POST to `/Financeiro/Fatura/ConsultarFaturas_AbaProdutoUpdateFilter` containing `CodigoTipoProduto`, `DataInicio`, `DataFim`, etc. to update the backend session filters.
2. **Grid Fetch**: Sends a POST to `/Financeiro/Fatura/ConsultarFaturas_AbaProdutoGridSTP` requesting pages and pagination options, returning a JSON listing of all invoices matching the filter date range.

### 5. Document Downloads
- **PDF File**: Sends a GET request to `/Financeiro/Fatura/ConsultarFaturas_ObterFaturaSTP?numeroFatura=FATURA_NUM` returning the PDF binary content directly.
- **Excel Spreadsheet**: Sends a POST request to `/Financeiro/Fatura/ConsultarFaturas_EnviarFaturaXlsSTP?numeroFatura=FATURA_NUM` with `obterMensagem: "false"`.
  - If the file is cached/ready, it returns a download hash `"Index"`. The client then downloads the spreadsheet by executing a GET request to `/report.aspx?hash={Index}`.
  - If not cached, the server automatically starts compiling it in the background and sends it to the customer email address.

---

## Production System Integration

Here is a template code snippet demonstrating how to import, configure, and integrate this client into your system (e.g., an automated daily/monthly scraping cron pipeline):

```python
import os
from semparar_api.semparar import SemPararEmpresasClient, SessionExpiredError, LoginError

def run_semparar_sync_pipeline():
    # 1. Initialize Client
    client = SemPararEmpresasClient(
        login_value=os.getenv("SEMPARAR_LOGIN_VALUE"),
        password=os.getenv("SEMPARAR_PASSWORD"),
        login_type="USERNAME",  # CNPJ, EMAIL, or USERNAME
        cookies_path="/var/secrets/semparar_cookies.json",
        twocaptcha_api_key=os.getenv("TWOCAPTCHA_API_KEY"),
        use_interactive_login=False  # Run strictly headless on background servers
    )

    try:
        # 2. Login
        print("Logging in/Re-using session cookies...")
        client.login()
        
        # 3. Retrieve Registration Information
        print("Syncing company registration...")
        account_data = client.get_account_data()
        company_name = account_data.get("Nome")
        cnpj = account_data.get("CnpjCpf")
        email = account_data.get("Email")
        print(f"Active Company: {company_name} | CNPJ: {cnpj} | Email: {email}")
        
        # 4. Fetch Invoices list
        print("Syncing invoices list...")
        invoices = client.get_invoices(
            product_type="STP",
            start_date="01/05/2026",
            end_date="30/06/2026"
        )
        
        # 5. Extract only closed/paid invoices (ignoring open items)
        closed_invoices = [inv for inv in invoices if inv.get("DescricaoSituacao") != "Em Aberto" and inv.get("Fatura")]
        
        if not closed_invoices:
            print("No closed invoices found in range.")
            return

        # Sort descending (Vencimento) to find the last closed invoice
        # Date helper function to sort (e.g. converting 15/06/2026 to 2026-06-15)
        def parse_date(d_str):
            p = d_str.split("/")
            return f"{p[2]}-{p[1]}-{p[0]}" if len(p) == 3 else "0000-00-00"
            
        closed_invoices.sort(key=lambda x: parse_date(x.get("Vencimento", "")), reverse=True)
        latest_closed = closed_invoices[0]
        fatura_num = latest_closed["Fatura"]
        
        print(f"Processing latest closed invoice: {fatura_num} (Due: {latest_closed['Vencimento']})")
        
        # 6. Download PDF Document
        pdf_bytes = client.download_invoice_pdf(fatura_num)
        # TODO: Save pdf_bytes to S3, Blob storage, Database, or filesystem
        # s3.put_object(Bucket='my-bucket', Key=f'invoices/{fatura_num}.pdf', Body=pdf_bytes)
        print(f"Downloaded PDF successfully: {len(pdf_bytes)} bytes.")
        
        # 7. Download Excel Spreadsheet
        xls_bytes = client.download_invoice_xls(fatura_num)
        if len(xls_bytes) > 0:
            # TODO: Save xls_bytes to your cloud storage
            print(f"Downloaded Excel successfully: {len(xls_bytes)} bytes.")
        else:
            print(f"Excel is being compiled by Sem Parar in background; will be emailed to {email}.")
            
    except SessionExpiredError as exp_err:
        # Action required: alert system admins to update cookies file manually 
        # or verify 2Captcha balance/API configurations.
        print(f"CRITICAL: Session expired and headless auto-renewal failed: {exp_err}")
        send_slack_alert(f"Sem Parar scraping session expired: {exp_err}")
        
    except LoginError as log_err:
        print(f"CRITICAL: Background login attempt rejected by server: {log_err}")
        
    except Exception as e:
        print(f"Error executing scraper pipeline: {e}")

def send_slack_alert(msg):
    # Stub placeholder for system notification integrations
    pass

if __name__ == "__main__":
    run_semparar_sync_pipeline()
```
