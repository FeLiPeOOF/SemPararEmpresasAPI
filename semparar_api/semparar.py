import os
import json
import time
import requests
from bs4 import BeautifulSoup

class SessionExpiredError(Exception):
    """Raised when the session is expired and cannot be auto-renewed without user action."""
    pass

class LoginError(Exception):
    """Raised when programmatic login fails."""
    pass

class SemPararEmpresasClient:
    """Client for Sem Parar Empresas portal to manage authentication and sessions."""
    
    def __init__(self, login_value, password, login_type="CNPJ", cookies_path="semparar_cookies.json", twocaptcha_api_key=None, use_interactive_login=True):
        self.login_value = login_value
        self.password = password
        self.login_type = login_type.upper()  # CNPJ, EMAIL, USERNAME
        self.cookies_path = cookies_path
        self.twocaptcha_api_key = twocaptcha_api_key
        self.use_interactive_login = use_interactive_login
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        })

    def _load_cookies(self) -> bool:
        """Loads cookies from a local file if it exists."""
        if os.path.exists(self.cookies_path):
            try:
                with open(self.cookies_path, "r") as f:
                    cookies = json.load(f)
                for cookie in cookies:
                    self.session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))
                print(f"Loaded cookies from {self.cookies_path}")
                return True
            except Exception as e:
                print(f"Failed to load cookies: {e}")
        return False

    def _save_cookies(self):
        """Saves session cookies to a local file."""
        try:
            cookies_list = []
            for cookie in self.session.cookies:
                cookies_list.append({
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "expires": cookie.expires,
                })
            with open(self.cookies_path, "w") as f:
                json.dump(cookies_list, f, indent=4)
            print(f"Saved cookies to {self.cookies_path}")
        except Exception as e:
            print(f"Failed to save cookies: {e}")

    def verify_session(self) -> bool:
        """Checks if the session is currently authenticated."""
        try:
            # Request the invoice list endpoint on the seguro subdomain.
            # If authenticated, it returns 200.
            # If not, it redirects (302) to the login screen.
            r = self.session.get(
                "https://seguro.sempararempresas.com.br/Financeiro/Fatura/ConsultarFaturas_AbaProdutoListarTipo",
                params={"codigoTipoProduto": "STP"},
                allow_redirects=False
            )
            return r.status_code == 200
        except Exception as e:
            print(f"Error verifying session: {e}")
            return False

    def _solve_captcha(self) -> str:
        """Solves MTCaptcha via 2Captcha API using direct HTTP requests."""
        if not self.twocaptcha_api_key:
            raise ValueError("2Captcha API key is not configured.")
        
        print("Submitting MTCaptcha to 2Captcha...")
        sitekey = "MTPublic-ABLdYsRql"
        page_url = "https://www.sempararempresas.com.br/login"
        
        in_url = "https://2captcha.com/in.php"
        res_url = "https://2captcha.com/res.php"
        
        params = {
            "key": self.twocaptcha_api_key,
            "method": "mtcaptcha",
            "sitekey": sitekey,
            "pageurl": page_url,
            "json": 1
        }
        
        r = requests.post(in_url, data=params)
        res = r.json()
        if res.get("status") != 1:
            raise LoginError(f"2Captcha submission failed: {res.get('request')}")
            
        task_id = res.get("request")
        print(f"MTCaptcha task created. Task ID: {task_id}. Polling for solution...")
        
        poll_params = {
            "key": self.twocaptcha_api_key,
            "action": "get",
            "id": task_id,
            "json": 1
        }
        
        # Poll up to 24 times (120 seconds max)
        for attempt in range(24):
            time.sleep(5)
            try:
                r_poll = requests.get(res_url, params=poll_params)
                poll_res = r_poll.json()
                status = poll_res.get("status")
                request_val = poll_res.get("request")
                
                if status == 1:
                    print("CAPTCHA solved successfully by 2Captcha!")
                    return request_val
                elif request_val == "CAPCHA_NOT_READY":
                    print(f"CAPTCHA not ready yet (attempt {attempt + 1}/24)...")
                else:
                    raise LoginError(f"2Captcha solving failed: {request_val}")
            except Exception as e:
                if "CAPCHA_NOT_READY" not in str(e):
                    print(f"Warning during polling: {e}")
                    
        raise LoginError("Timed out waiting for 2Captcha to solve the CAPTCHA.")

    def interactive_login(self) -> bool:
        """Opens a headful browser window to let the user log in and solve CAPTCHA manually.
        Once the login is successful, extracts the cookies, saves them, and closes the browser.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise Exception("Playwright is not installed. Please install it using 'pip install playwright' and run 'playwright install'.")
            
        print("\n" + "="*80)
        print("LAUNCHING INTERACTIVE LOGIN WINDOW")
        print("Please solve the CAPTCHA in the browser window to log in.")
        print("="*80 + "\n")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(user_agent=self.session.headers.get("User-Agent"))
            page = context.new_page()
            
            page.goto("https://www.sempararempresas.com.br/login")
            
            # Autofill credentials
            try:
                # Wait for input fields to be visible
                page.wait_for_selector("#password", timeout=10000)
                
                if self.login_type == "CNPJ":
                    cnpj_tab = page.locator("label:has-text('CNPJ')").first or page.locator("text=CNPJ").first
                    if cnpj_tab.is_visible():
                        cnpj_tab.click()
                    page.fill("#UserCNPJ", self.login_value)
                elif self.login_type == "EMAIL":
                    email_tab = page.locator("label:has-text('E-mail')").first or page.locator("text=E-mail").first
                    if email_tab.is_visible():
                        email_tab.click()
                    page.fill("#UserEmail", self.login_value)
                else:
                    user_tab = page.locator("label:has-text('Login')").first or page.locator("text=Login").first
                    if user_tab.is_visible():
                        user_tab.click()
                    page.fill("#UserName", self.login_value)
                
                page.fill("#password", self.password)
            except Exception as fill_err:
                print(f"Warning: could not autofill login fields: {fill_err}")
                
            # Wait for user to log in and get redirected to the portal (5 minutes timeout)
            try:
                page.wait_for_url("**/portal.sempararempresas.com.br/**", timeout=300000)
                print("Login successful! Establishing session for seguro subdomain...")
                
                # Navigate to the seguro subdomain to get the ASP.NET_SessionId
                page.goto("https://seguro.sempararempresas.com.br/Financeiro/Fatura/ConsultarFaturas_AbaProdutoListarTipo?codigoTipoProduto=STP", wait_until="networkidle")
                
                # Extract cookies
                pw_cookies = context.cookies()
                
                # Format cookies for requests session
                cookies_list = []
                for c in pw_cookies:
                    cookies_list.append({
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c["domain"],
                        "path": c["path"],
                        "expires": c.get("expires", -1),
                    })
                    
                # Update requests session cookies
                for cookie in cookies_list:
                    self.session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))
                    
                # Save cookies to file
                self._save_cookies()
                return True
            except Exception as wait_err:
                print(f"Interactive login failed or timed out: {wait_err}")
                return False
            finally:
                browser.close()

    def login(self) -> bool:
        """Logs into Sem Parar Empresas portal.

        First attempts to reuse cached cookies. If cookies are expired or missing,
        automatically performs interactive login (or background login using 2Captcha if API key is set).
        """
        # Try loading cached session
        if self._load_cookies():
            if self.verify_session():
                print("Session cookies are valid. Login bypassed.")
                return True
            else:
                print("Cached session cookies are expired or invalid.")
                
        # Perform programmatic background login if key is provided
        if not self.twocaptcha_api_key:
            if self.use_interactive_login:
                try:
                    success = self.interactive_login()
                    if success:
                        return True
                except Exception as e:
                    print(f"Interactive login attempt failed: {e}")
                    
            raise SessionExpiredError(
                "Sem Parar session is expired/missing, and no 2Captcha API key is configured. "
                "Please configure a 2Captcha API key or perform interactive login."
            )
            
        print("Attempting background programmatic login...")
        
        # 1. Fetch login page to get CSRF token
        try:
            r = self.session.get("https://www.sempararempresas.com.br/login")
            soup = BeautifulSoup(r.text, "html.parser")
            token_input = soup.find("input", {"name": "__RequestVerificationToken"})
            if not token_input:
                raise LoginError("Could not find __RequestVerificationToken on login page.")
            token = token_input.get("value")
        except Exception as e:
            raise LoginError(f"Failed to fetch login page: {e}")
            
        # 2. Solve CAPTCHA in background
        captcha_token = self._solve_captcha()
        
        # 3. Construct login payload
        payload = {
            "__RequestVerificationToken": token,
            "Email": self.login_value if self.login_type == "EMAIL" else "",
            "UserName": self.login_value if self.login_type in ("CNPJ", "USERNAME") else "",
            "password": self.password,
            "mtcaptcha-verifiedtoken": captcha_token,
            "validaCaptcha": "false",
            "siteTokenCaptcha": "",
            "RedirectUrl": ""
        }
        
        # 4. POST login form
        headers = {
            "Referer": "https://www.sempararempresas.com.br/login",
            "Origin": "https://www.sempararempresas.com.br",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            r_post = self.session.post(
                "https://www.sempararempresas.com.br/Login/Index",
                data=payload,
                headers=headers,
                allow_redirects=False
            )
            
            # Redirection (302) signals successful login
            if r_post.status_code in (301, 302):
                redirect_url = r_post.headers.get("Location", "")
                print(f"Login successful. Redirected to: {redirect_url}")
                
                # Follow redirect to establish session cookies fully
                self.session.get(f"https://www.sempararempresas.com.br{redirect_url}" if redirect_url.startswith("/") else redirect_url)
                
                if self.verify_session():
                    self._save_cookies()
                    return True
                else:
                    raise LoginError("Redirected, but session verification failed.")
            else:
                # Parse server side JSON or HTML error response
                try:
                    res_json = r_post.json()
                    error_msg = res_json.get("Erro", "Unknown authentication error")
                except Exception:
                    error_msg = "Unknown authentication error"
                raise LoginError(f"Login failed: {error_msg}")
                
        except Exception as e:
            if isinstance(e, LoginError):
                raise e
            raise LoginError(f"HTTP request failed during login: {e}")

    def get_account_data(self) -> dict:
        """Retrieves and parses account cadastral data from portal."""
        if not self.verify_session():
            self.login()
            
        url = "https://seguro.sempararempresas.com.br/SemParar/DadosCliente/DadosSemParar_AbaDadosCadastrais"
        print(f"Fetching account data from {url}...")
        r = self.session.get(url)
        
        if r.status_code != 200:
            raise Exception(f"Failed to fetch account data. Status code: {r.status_code}")
            
        soup = BeautifulSoup(r.text, "html.parser")
        data = {}
        
        # Parse standard form controls (inputs, textareas, selects)
        for element in soup.find_all(["input", "select", "textarea"]):
            if element.name == "input" and element.get("type") == "hidden":
                continue
                
            element_id = element.get("id")
            name = element.get("name")
            value = element.get("value", "")
            
            if element.name == "textarea":
                value = element.text.strip()
            elif element.name == "select":
                selected_opt = element.find("option", selected=True)
                if selected_opt:
                    value = selected_opt.text.strip()
                elif element.find("option"):
                    value = element.find("option").text.strip()
            
            key = None
            if element_id:
                label = soup.find("label", {"for": element_id})
                if label:
                    key = label.get_text().strip().replace(":", "")
                    
            if not key and name:
                key = name
            if not key and element_id:
                key = element_id
                
            if key:
                data[key] = value.strip()
                
        # Parse table key-values if present
        for row in soup.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if th and td:
                key = th.get_text().strip().replace(":", "")
                val = td.get_text().strip()
                if key and val:
                    data[key] = val
                    
        if not data:
            data["_raw_title"] = soup.title.string.strip() if soup.title else ""
            data["_raw_text"] = soup.get_text()
            
        return data

    def get_invoices(self, product_type="STP", start_date=None, end_date=None, extra_params=None) -> list:
        """Retrieves and parses invoices for the specified product type.

        Allows filtering by date (start_date/end_date) if supported.
        """
        if not self.verify_session():
            self.login()
            
        # 1. Update filter state on the server
        filter_url = "https://seguro.sempararempresas.com.br/Financeiro/Fatura/ConsultarFaturas_AbaProdutoUpdateFilter"
        filter_payload = {
            "CodigoTipoProduto": product_type,
            "DataInicio": start_date or "",
            "DataFim": end_date or "",
            "NumeroFatura": "",
            "Situacao": ""
        }
        if extra_params:
            filter_payload.update(extra_params)
            
        print(f"Updating invoice filters at {filter_url}...")
        try:
            r_filter = self.session.post(filter_url, data=filter_payload)
            print(f"Filter update status: {r_filter.status_code}")
        except Exception as e:
            print(f"Warning: Failed to update invoice filters: {e}")
            
        # 2. Query grid JSON data
        grid_url = "https://seguro.sempararempresas.com.br/Financeiro/Fatura/ConsultarFaturas_AbaProdutoGridSTP"
        grid_params = {"codigoTipoProduto": product_type}
        
        grid_payload = {
            "page": "1",
            "pageSize": "100",
            "sort": "Vencimento-asc",
            "group": "",
            "filter": "",
            "DataInicio": start_date or "",
            "DataFim": end_date or "",
            "NumeroFatura": "",
            "Situacao": "",
            "CodigoTipoProduto": product_type
        }
        
        print(f"Fetching invoices grid from {grid_url}...")
        r = self.session.post(grid_url, params=grid_params, data=grid_payload)
        
        if r.status_code != 200:
            raise Exception(f"Failed to fetch invoices. Status code: {r.status_code}")
            
        try:
            res_json = r.json()
            raw_data = []
            if isinstance(res_json, dict) and "Data" in res_json:
                raw_data = res_json["Data"]
            elif isinstance(res_json, list):
                raw_data = res_json
                
            invoices = []
            for item in raw_data:
                # Map Kendo JSON properties to standard keys and format them
                vencimento_raw = item.get("Vencimento", "")
                vencimento_formatted = vencimento_raw
                if vencimento_raw and "T" in vencimento_raw:
                    # e.g., "2026-06-15T00:00:00" -> "15/06/2026"
                    try:
                        date_part = vencimento_raw.split("T")[0]
                        parts = date_part.split("-")
                        if len(parts) == 3:
                            vencimento_formatted = f"{parts[2]}/{parts[1]}/{parts[0]}"
                    except Exception:
                        pass
                
                num_fatura = item.get("NumeroFatura")
                num_fatura_str = str(num_fatura) if num_fatura is not None else ""
                
                # Format money/total values
                val_total = item.get("ValorTotal", 0.0)
                
                invoice_dict = {
                    "Fatura": num_fatura_str,
                    "Nº Fatura": num_fatura_str,
                    "Vencimento": vencimento_formatted,
                    "Valor": f"R$ {val_total:.2f}".replace(".", ","),
                    "Valor Total (R$)": f"R$ {val_total:.2f}".replace(".", ","),
                    "ValorTotal": val_total,
                    "Situação": item.get("DescricaoSituacao", ""),
                    "DescricaoSituacao": item.get("DescricaoSituacao", ""),
                    "MesAno": item.get("MesAno", ""),
                    "Pedágio (R$)": item.get("ValorPedagio", 0.0),
                    "Estacionamento (R$)": item.get("ValorEstacionamento", 0.0),
                    "Abastecimento (R$)": item.get("ValorAbastecimento", 0.0),
                    "Outros Serviços (R$)": item.get("ValorOutrosServicos", 0.0),
                }
                
                if num_fatura_str:
                    pdf_link = f"https://seguro.sempararempresas.com.br/Financeiro/Fatura/ConsultarFaturas_ObterFaturaSTP?numeroFatura={num_fatura_str}"
                    invoice_dict["Ações"] = "Fatura PDF"
                    invoice_dict["Ações_link"] = pdf_link
                    invoice_dict["FaturaPDF_link"] = pdf_link
                    
                invoices.append(invoice_dict)
                
            return invoices
        except ValueError:
            pass
            
        soup = BeautifulSoup(r.text, "html.parser")
        invoices = []
        
        tables = soup.find_all("table")
        for table in tables:
            headers = []
            thead = table.find("thead")
            if thead:
                headers = [th.get_text().strip() for th in thead.find_all("th")]
            else:
                first_tr = table.find("tr")
                if first_tr:
                    headers = [th_td.get_text().strip() for th_td in first_tr.find_all(["th", "td"])]
                    
            rows = table.find_all("tr")
            if not headers and rows:
                first_row_cells = rows[0].find_all(["td", "th"])
                headers = [f"column_{i}" for i in range(len(first_row_cells))]
                
            start_idx = 1 if not thead and rows else 0
            tbody = table.find("tbody")
            tr_list = tbody.find_all("tr") if tbody else rows[start_idx:]
            
            for tr in tr_list:
                cells = tr.find_all("td")
                if not cells:
                    continue
                row_data = {}
                for idx, cell in enumerate(cells):
                    header_name = headers[idx] if idx < len(headers) else f"column_{idx}"
                    link = cell.find("a")
                    if link and link.get("href"):
                        href = link.get("href")
                        if href.startswith("/"):
                            href = f"https://seguro.sempararempresas.com.br{href}"
                        row_data[f"{header_name}_link"] = href
                        
                    row_data[header_name] = cell.get_text().strip()
                invoices.append(row_data)
                
        return invoices

    def download_invoice_pdf(self, invoice_number: str) -> bytes:
        """Downloads the PDF of a closed invoice by its number.
        
        Returns the binary content of the PDF.
        """
        if not self.verify_session():
            self.login()
            
        url = "https://seguro.sempararempresas.com.br/Financeiro/Fatura/ConsultarFaturas_ObterFaturaSTP"
        params = {"numeroFatura": invoice_number}
        print(f"Downloading PDF for invoice {invoice_number}...")
        r = self.session.get(url, params=params)
        
        # Check that we got a valid response (not redirected to login/error page which is small)
        if r.status_code != 200 or len(r.content) < 5000:
            raise Exception(f"Failed to download PDF. Status: {r.status_code}, length: {len(r.content)}")
            
        return r.content

    def download_invoice_xls(self, invoice_number: str, email: str = None) -> bytes:
        """Downloads the Excel (XLS) file of a closed invoice by its number.
        
        Requires triggering report generation via POST and then downloading by hash index.
        Returns the binary content of the Excel sheet.
        """
        if not self.verify_session():
            self.login()
            
        # Get email to satisfy the form parameter
        if not email:
            try:
                account_data = self.get_account_data()
                email = account_data.get("Email")
            except Exception:
                pass
        if not email:
            email = "email@example.com"  # Fallback dummy email if none is found
            
        # 1. Trigger generation via POST
        trigger_url = f"https://seguro.sempararempresas.com.br/Financeiro/Fatura/ConsultarFaturas_EnviarFaturaXlsSTP?numeroFatura={invoice_number}"
        payload = {
            "obterMensagem": "false",
            "emailDestino": email
        }
        print(f"Triggering Excel generation for invoice {invoice_number} (email: {email})...")
        r_trigger = self.session.post(trigger_url, data=payload)
        
        if r_trigger.status_code != 200:
            raise Exception(f"Failed to trigger Excel generation. Status code: {r_trigger.status_code}")
            
        try:
            res_json = r_trigger.json()
            if res_json.get("Erros"):
                raise Exception(f"Server returned errors triggering Excel: {res_json.get('Erros')}")
                
            hash_index = res_json.get("Index")
            if not hash_index:
                if res_json.get("PossuiSolicitacao") is False:
                    print(f"Excel generation triggered successfully. The file is being processed and will be sent to {email}.")
                    return b""
                raise Exception("Did not receive a download hash index in the server response.")
        except Exception as e:
            raise Exception(f"Failed to parse Excel trigger response: {e}. Raw response: {r_trigger.text[:500]}")
            
        # 2. Download by hash index
        download_url = f"https://seguro.sempararempresas.com.br/report.aspx?hash={hash_index}"
        print(f"Downloading Excel from {download_url}...")
        r_download = self.session.get(download_url)
        
        if r_download.status_code != 200 or len(r_download.content) == 0:
            raise Exception(f"Failed to download Excel file. Status: {r_download.status_code}")
            
        return r_download.content

    def trigger_open_invoice_xls(self, email: str = None) -> dict:
        """Triggers the Excel report of open items ('Itens a Faturar') to be generated and sent via email.
        
        Returns the JSON response from the server.
        """
        if not self.verify_session():
            self.login()
            
        if not email:
            try:
                account_data = self.get_account_data()
                email = account_data.get("Email")
            except Exception:
                pass
        if not email:
            raise ValueError("An email address is required to receive the open invoice Excel report.")
            
        url = "https://seguro.sempararempresas.com.br/Financeiro/Fatura/ConsultarFaturas_EnviarItensFaturarXlsSTP"
        payload = {
            "email": email,
            "mensagem": "Relatório de Itens a Faturar"
        }
        print(f"Triggering open invoice (Itens a Faturar) Excel report to {email}...")
        r = self.session.post(url, data=payload)
        
        if r.status_code != 200:
            raise Exception(f"Failed to trigger open invoice Excel. Status code: {r.status_code}")
            
        try:
            res_json = r.json()
            if res_json.get("Erros"):
                raise Exception(f"Server returned errors: {res_json.get('Erros')}")
            return res_json
        except Exception as e:
            raise Exception(f"Failed to parse trigger response: {e}. Raw: {r.text[:500]}")
