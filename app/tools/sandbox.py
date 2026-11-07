import os
import subprocess
import uuid
import config

SANDBOX_DIR = os.path.join(config.RUNTIME_DIR, "sandbox")

def execute_python(code):
    """Salva e executa um script Python escrito pela Hoshino."""
    os.makedirs(SANDBOX_DIR, exist_ok=True)
    file_name = f"script_{uuid.uuid4().hex[:8]}.py"
    file_path = os.path.join(SANDBOX_DIR, file_name)
    
    # Salva o código gerado pelo LLM em um arquivo
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code)
    
    try:
        # Executa o arquivo isoladamente usando o python3 do sistema
        result = subprocess.run(["python3", file_path], capture_output=True, text=True, timeout=10)
        output = result.stdout if result.stdout else result.stderr
        
        return output.strip() if output else "Script executado com sucesso (sem saída visível)."
    except subprocess.TimeoutExpired:
        return "Erro: O script demorou muito para executar e foi interrompido (Timeout de 10s)."
    except Exception as e:
        return f"Erro na execução do script: {str(e)}"
