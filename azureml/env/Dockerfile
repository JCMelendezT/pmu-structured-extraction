FROM python:3.12-slim

# Las dependencias del servicio de inferencia, resueltas y bloqueadas por uv.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# azureml-mlflow conecta las corridas con el tracking del workspace.
# azure-identity y azure-keyvault-secrets son los que permiten que el job lea
# groq-api-key del Key Vault con su identidad administrada. El permiso se
# otorga aparte, con az keyvault set-policy; la imagen no lo configuraba.
RUN pip install --no-cache-dir azureml-mlflow azure-identity azure-keyvault-secrets pyyaml
