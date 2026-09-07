# Sistema de Reconhecimento Facial

## Instalação

Recomendado: Python 3.10 ou 3.11 em ambiente virtual.

### Windows

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Executar

```bat
python cadastro.py
```

## Uso

1. Escolha `1` para cadastrar um aluno.
2. Digite nome e ID/matrícula numérica.
3. Posicione apenas um rosto na câmera.
4. Pressione ESPAÇO para capturar.
5. Escolha `2` para iniciar o reconhecimento.
6. Quando o aluno for reconhecido, pressione ENTER para registrar a presença.
7. ESC fecha a câmera.

A pasta `fotos` é criada automaticamente.

## Observações

- A câmera precisa estar disponível para o computador.
- Na primeira execução, o DeepFace pode baixar os modelos e demorar.
- O banco `escola.db` é local e foi mantido separado do arquivo original.
