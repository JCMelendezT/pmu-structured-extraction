FROM python:3.12-slim

# Las dependencias del servicio de inferencia, resueltas y bloqueadas por uv.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# azureml-mlflow conecta las corridas con el tracking del workspace.
# azure-ai-ml aporta el MLClient con el que registrar.py escribe el modelo
# ganador. azure-identity y azure-keyvault-secrets son los que permiten que el
# job lea groq-api-key del Key Vault con su identidad administrada. El permiso
# se otorga aparte, con az keyvault set-policy; la imagen no lo configuraba.
#
# azure-ai-ml va aqui y no en requirements.txt a proposito: ese archivo se
# regenera con uv export -o y cualquier dependencia agregada a mano desaparece
# en la siguiente regeneracion.
RUN pip install --no-cache-dir azureml-mlflow azure-ai-ml azure-identity azure-keyvault-secrets pyyaml
