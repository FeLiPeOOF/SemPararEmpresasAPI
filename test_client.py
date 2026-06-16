import os
import json
from semparar_api.semparar import SemPararEmpresasClient, SessionExpiredError, LoginError

class RaisesContext:
    """Custom context manager to assert exceptions without requiring external libraries."""
    def __init__(self, expected_exception):
        self.expected_exception = expected_exception
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            raise AssertionError(f"Expected exception {self.expected_exception.__name__} was not raised")
        if not issubclass(exc_type, self.expected_exception):
            return False  # Let other exceptions propagate
        self.value = exc_val
        return True  # Suppress the expected exception

def test_expired_session_raises_expired_error():
    # Initialize client with mock credentials and no 2Captcha key
    client = SemPararEmpresasClient(
        login_value="12345678000199",
        password="mock_password",
        login_type="CNPJ",
        cookies_path="non_existent_cookies.json",
        twocaptcha_api_key=None,
        use_interactive_login=False
    )
    
    # Should raise SessionExpiredError since cookies don't exist and key is missing
    with RaisesContext(SessionExpiredError) as exc_info:
        client.login()
        
    assert "no 2Captcha API key is configured" in str(exc_info.value)

def test_invalid_cookies_fallback():
    # Create an invalid cookie file
    temp_cookies = "temp_invalid_cookies.json"
    with open(temp_cookies, "w") as f:
        json.dump([{"name": "mock_cookie", "value": "mock_val", "domain": "www.sempararempresas.com.br"}], f)
        
    client = SemPararEmpresasClient(
        login_value="12345678000199",
        password="mock_password",
        login_type="CNPJ",
        cookies_path=temp_cookies,
        twocaptcha_api_key=None,
        use_interactive_login=False
    )
    
    # Should load cookies, detect session is invalid, then fail with SessionExpiredError
    with RaisesContext(SessionExpiredError) as exc_info:
        client.login()
        
    assert "Sem Parar session is expired/missing" in str(exc_info.value)
    
    # Clean up
    if os.path.exists(temp_cookies):
        os.remove(temp_cookies)

def test_invalid_2captcha_key():
    client = SemPararEmpresasClient(
        login_value="12345678000199",
        password="mock_password",
        login_type="CNPJ",
        cookies_path="non_existent_cookies.json",
        twocaptcha_api_key="INVALID_KEY_FORMAT_MOCK",
        use_interactive_login=False
    )
    
    # Should attempt programmatic login, submit to 2Captcha, and raise LoginError due to invalid key
    with RaisesContext(LoginError) as exc_info:
        client.login()
        
    assert "2Captcha submission failed" in str(exc_info.value) or "ERROR_KEY_DOES_NOT_EXIST" in str(exc_info.value)

def test_get_account_data_parsing():
    from unittest.mock import MagicMock
    client = SemPararEmpresasClient(
        login_value="12345678000199",
        password="mock_password",
        login_type="CNPJ",
        cookies_path="non_existent_cookies.json",
        twocaptcha_api_key=None,
        use_interactive_login=False
    )
    
    client.verify_session = MagicMock(return_value=True)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = """
    <html>
      <head><title>Registration</title></head>
      <body>
        <form>
          <label for="RazaoSocial">Razão Social:</label>
          <input type="text" id="RazaoSocial" name="RazaoSocial" value="EMPRESA EXEMPLO LTDA" />
          
          <label for="CNPJ">CNPJ da Empresa:</label>
          <input type="text" id="CNPJ" name="CNPJ" value="12.345.678/0001-99" />
          
          <input type="hidden" name="token" value="hidden_value" />
        </form>
        <table>
          <tr>
            <th>Inscrição Estadual</th>
            <td>ISENTO</td>
          </tr>
        </table>
      </body>
    </html>
    """
    client.session.get = MagicMock(return_value=mock_response)
    
    data = client.get_account_data()
    
    assert data.get("Razão Social") == "EMPRESA EXEMPLO LTDA"
    assert data.get("CNPJ da Empresa") == "12.345.678/0001-99"
    assert data.get("Inscrição Estadual") == "ISENTO"
    assert "token" not in data

def test_get_invoices_html_table_parsing():
    from unittest.mock import MagicMock
    client = SemPararEmpresasClient(
        login_value="12345678000199",
        password="mock_password",
        login_type="CNPJ",
        cookies_path="non_existent_cookies.json",
        twocaptcha_api_key=None,
        use_interactive_login=False
    )
    
    client.verify_session = MagicMock(return_value=True)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(side_effect=ValueError("No JSON"))
    
    mock_response.text = """
    <html>
      <body>
        <table>
          <thead>
            <tr>
              <th>Fatura</th>
              <th>Vencimento</th>
              <th>Valor</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>123456</td>
              <td>10/08/2026</td>
              <td>R$ 150,00</td>
              <td><a href="/Financeiro/Fatura/Download?id=123456">Baixar PDF</a></td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    client.session.post = MagicMock(return_value=mock_response)
    
    invoices = client.get_invoices(product_type="STP")
    
    assert len(invoices) == 1
    assert invoices[0].get("Fatura") == "123456"
    assert invoices[0].get("Vencimento") == "10/08/2026"
    assert invoices[0].get("Valor") == "R$ 150,00"
    assert invoices[0].get("Ações") == "Baixar PDF"
    assert invoices[0].get("Ações_link") == "https://seguro.sempararempresas.com.br/Financeiro/Fatura/Download?id=123456"

def test_get_invoices_json_parsing():
    from unittest.mock import MagicMock
    client = SemPararEmpresasClient(
        login_value="12345678000199",
        password="mock_password",
        login_type="CNPJ",
        cookies_path="non_existent_cookies.json",
        twocaptcha_api_key=None,
        use_interactive_login=False
    )
    
    client.verify_session = MagicMock(return_value=True)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "Data": [
            {
                "NumeroFatura": "26129838267",
                "Vencimento": "2026-06-15T00:00:00",
                "ValorPedagio": 3800.28,
                "ValorEstacionamento": 260.0,
                "ValorAbastecimento": 81.0,
                "ValorOutrosServicos": 369.5,
                "ValorTotal": 4510.78,
                "DescricaoSituacao": "Paga",
                "MesAno": "jun/2026",
            }
        ]
    })
    
    client.session.post = MagicMock(return_value=mock_response)
    
    invoices = client.get_invoices(product_type="STP")
    
    assert len(invoices) == 1
    assert invoices[0].get("Fatura") == "26129838267"
    assert invoices[0].get("Vencimento") == "15/06/2026"
    assert invoices[0].get("Valor") == "R$ 4510,78"
    assert invoices[0].get("Situação") == "Paga"
    assert invoices[0].get("Ações") == "Fatura PDF"
    assert invoices[0].get("Ações_link") == "https://seguro.sempararempresas.com.br/Financeiro/Fatura/ConsultarFaturas_ObterFaturaSTP?numeroFatura=26129838267"

def test_get_invoices_date_filters():
    from unittest.mock import MagicMock
    client = SemPararEmpresasClient(
        login_value="12345678000199",
        password="mock_password",
        login_type="CNPJ",
        cookies_path="non_existent_cookies.json",
        twocaptcha_api_key=None,
        use_interactive_login=False
    )
    
    client.verify_session = MagicMock(return_value=True)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={})
    
    client.session.post = MagicMock(return_value=mock_response)
    
    # Run with filters
    client.get_invoices(product_type="STP", start_date="01/05/2026", end_date="31/05/2026")
    
    # Assert post was called twice
    assert client.session.post.call_count == 2
    
    # Check first call (update filter)
    filter_args, filter_kwargs = client.session.post.call_args_list[0]
    assert "ConsultarFaturas_AbaProdutoUpdateFilter" in filter_args[0]
    assert filter_kwargs.get("data", {}).get("DataInicio") == "01/05/2026"
    assert filter_kwargs.get("data", {}).get("DataFim") == "31/05/2026"
    
    # Check second call (grid query)
    grid_args, grid_kwargs = client.session.post.call_args_list[1]
    assert "ConsultarFaturas_AbaProdutoGridSTP" in grid_args[0]
    assert grid_kwargs.get("params", {}).get("codigoTipoProduto") == "STP"
    assert grid_kwargs.get("data", {}).get("DataInicio") == "01/05/2026"
    assert grid_kwargs.get("data", {}).get("DataFim") == "31/05/2026"

def test_download_invoice_pdf():
    from unittest.mock import MagicMock
    client = SemPararEmpresasClient(
        login_value="12345678000199",
        password="mock_password",
        login_type="CNPJ",
        cookies_path="non_existent_cookies.json",
        twocaptcha_api_key=None,
        use_interactive_login=False
    )
    client.verify_session = MagicMock(return_value=True)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"%PDF-1.4 mock pdf data content" * 200
    client.session.get = MagicMock(return_value=mock_response)
    
    pdf_bytes = client.download_invoice_pdf("12345")
    assert pdf_bytes == b"%PDF-1.4 mock pdf data content" * 200
    
    client.session.get.assert_called_once()
    args, kwargs = client.session.get.call_args
    assert "ConsultarFaturas_ObterFaturaSTP" in args[0]
    assert kwargs.get("params", {}).get("numeroFatura") == "12345"

def test_download_invoice_xls():
    from unittest.mock import MagicMock
    client = SemPararEmpresasClient(
        login_value="12345678000199",
        password="mock_password",
        login_type="CNPJ",
        cookies_path="non_existent_cookies.json",
        twocaptcha_api_key=None,
        use_interactive_login=False
    )
    client.verify_session = MagicMock(return_value=True)
    client.get_account_data = MagicMock(return_value={"Email": "mock@example.com"})
    
    # Mock trigger response
    mock_trigger_res = MagicMock()
    mock_trigger_res.status_code = 200
    mock_trigger_res.json = MagicMock(return_value={"Index": "MOCK_HASH_123", "PossuiSolicitacao": True})
    
    # Mock download response
    mock_download_res = MagicMock()
    mock_download_res.status_code = 200
    mock_download_res.content = b"mock xls content"
    
    # Handle sequential calls
    client.session.post = MagicMock(return_value=mock_trigger_res)
    client.session.get = MagicMock(return_value=mock_download_res)
    
    xls_bytes = client.download_invoice_xls("12345")
    assert xls_bytes == b"mock xls content"
    
    # Check trigger call
    client.session.post.assert_called_once()
    post_args, post_kwargs = client.session.post.call_args
    assert "ConsultarFaturas_EnviarFaturaXlsSTP" in post_args[0]
    assert "12345" in post_args[0]
    assert post_kwargs.get("data", {}).get("emailDestino") == "mock@example.com"
    
    # Check download call
    client.session.get.assert_called_once()
    get_args, get_kwargs = client.session.get.call_args
    assert "report.aspx" in get_args[0]
    assert "hash=MOCK_HASH_123" in get_args[0]

def test_trigger_open_invoice_xls():
    from unittest.mock import MagicMock
    client = SemPararEmpresasClient(
        login_value="12345678000199",
        password="mock_password",
        login_type="CNPJ",
        cookies_path="non_existent_cookies.json",
        twocaptcha_api_key=None,
        use_interactive_login=False
    )
    client.verify_session = MagicMock(return_value=True)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"Mensagem": "Success", "Erros": None})
    client.session.post = MagicMock(return_value=mock_response)
    
    res = client.trigger_open_invoice_xls("mock@example.com")
    assert res.get("Mensagem") == "Success"
    
    client.session.post.assert_called_once()
    post_args, post_kwargs = client.session.post.call_args
    assert "ConsultarFaturas_EnviarItensFaturarXlsSTP" in post_args[0]
    assert post_kwargs.get("data", {}).get("email") == "mock@example.com"

if __name__ == "__main__":
    print("Running tests...")
    try:
        test_expired_session_raises_expired_error()
        print("test_expired_session_raises_expired_error: PASSED")
        
        test_invalid_cookies_fallback()
        print("test_invalid_cookies_fallback: PASSED")
        
        test_invalid_2captcha_key()
        print("test_invalid_2captcha_key: PASSED")
        
        test_get_account_data_parsing()
        print("test_get_account_data_parsing: PASSED")
        
        test_get_invoices_html_table_parsing()
        print("test_get_invoices_html_table_parsing: PASSED")
        
        test_get_invoices_json_parsing()
        print("test_get_invoices_json_parsing: PASSED")
        
        test_get_invoices_date_filters()
        print("test_get_invoices_date_filters: PASSED")
        
        test_download_invoice_pdf()
        print("test_download_invoice_pdf: PASSED")
        
        test_download_invoice_xls()
        print("test_download_invoice_xls: PASSED")
        
        test_trigger_open_invoice_xls()
        print("test_trigger_open_invoice_xls: PASSED")
        
        print("\nAll unit tests passed successfully!")
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
