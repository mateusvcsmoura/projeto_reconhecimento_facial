import os
import sqlite3
import cv2
from deepface import DeepFace

# ============================================================
# CONFIGURAÇÃO
# ============================================================

PROJETO = os.path.dirname(os.path.abspath(__file__))
CAMINHO_DB = os.path.join(PROJETO, "escola.db")
PASTA_FOTOS = os.path.join(PROJETO, "fotos")

# Facenet512 costuma ter boa precisão, mas é mais pesado.
MODELO = "Facenet512"
DETECTOR = "opencv"

os.makedirs(PASTA_FOTOS, exist_ok=True)


# ============================================================
# BANCO DE DADOS
# ============================================================

def conectar():
    return sqlite3.connect(CAMINHO_DB)


def preparar_banco():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alunos (
            id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            foto_path TEXT NOT NULL,
            biometria_id INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS presencas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER NOT NULL,
            data_hora TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# CADASTRO FACIAL
# ============================================================

def cadastrar_aluno():
    print("\n=== CADASTRO DE ALUNO ===")

    nome = input("Nome do aluno: ").strip()

    if not nome:
        print("ERRO: informe o nome.")
        return

    try:
        aluno_id = int(input("ID/matrícula numérica: ").strip())
    except ValueError:
        print("ERRO: o ID precisa ser numérico.")
        return

    caminho_foto = os.path.join(PASTA_FOTOS, f"{aluno_id}.jpg")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM alunos WHERE id = ?", (aluno_id,))
    if cursor.fetchone():
        conn.close()
        print("ERRO: já existe um aluno com esse ID.")
        return

    conn.close()

    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        print("ERRO: não foi possível abrir a câmera.")
        return

    print("\nPosicione o rosto dentro da câmera.")
    print("Pressione ESPAÇO para tirar a foto.")
    print("Pressione ESC para cancelar.")

    foto_capturada = False

    while True:
        ok, frame = camera.read()

        if not ok:
            print("ERRO: não foi possível ler a câmera.")
            break

        cv2.putText(
            frame,
            "ESPACO = cadastrar | ESC = cancelar",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        cv2.imshow("Cadastro facial", frame)

        tecla = cv2.waitKey(1) & 0xFF

        if tecla == 27:  # ESC
            break

        if tecla == 32:  # ESPAÇO
            try:
                # Confirma se existe exatamente um rosto na imagem.
                resultado = DeepFace.extract_faces(
                    img_path=frame,
                    detector_backend=DETECTOR,
                    enforce_detection=True,
                    align=True
                )

                if len(resultado) != 1:
                    print("ERRO: deixe somente UM rosto na câmera.")
                    continue

                cv2.imwrite(caminho_foto, frame)
                foto_capturada = True
                print(f"Foto salva em: {caminho_foto}")
                break

            except Exception as erro:
                print("ERRO: não foi possível detectar um rosto.")
                print(f"Detalhes: {erro}")

    camera.release()
    cv2.destroyAllWindows()

    if not foto_capturada:
        print("Cadastro cancelado.")
        return

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO alunos (id, nome, foto_path, biometria_id)
        VALUES (?, ?, ?, ?)
        """,
        (aluno_id, nome, caminho_foto, aluno_id)
    )

    conn.commit()
    conn.close()

    print("\nCADASTRO REALIZADO COM SUCESSO!")
    print(f"Aluno: {nome}")
    print(f"ID: {aluno_id}")
    print(f"Foto: {caminho_foto}")


# ============================================================
# RECONHECIMENTO FACIAL
# ============================================================

def registrar_presenca(aluno_id):
    from datetime import datetime

    conn = conectar()
    cursor = conn.cursor()

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Evita registrar várias presenças seguidas no mesmo dia.
    cursor.execute(
        """
        SELECT id
        FROM presencas
        WHERE aluno_id = ?
          AND date(data_hora) = date(?)
        LIMIT 1
        """,
        (aluno_id, agora)
    )

    ja_registrada = cursor.fetchone()

    if not ja_registrada:
        cursor.execute(
            """
            INSERT INTO presencas (aluno_id, data_hora)
            VALUES (?, ?)
            """,
            (aluno_id, agora)
        )
        conn.commit()
        print("Presença registrada!")
    else:
        print("Presença já registrada hoje.")

    conn.close()


def reconhecer_alunos():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, nome, foto_path FROM alunos ORDER BY nome"
    )

    alunos = cursor.fetchall()
    conn.close()

    if not alunos:
        print("Nenhum aluno cadastrado.")
        return

    # Remove referências para fotos que não existem.
    alunos_validos = []

    for aluno_id, nome, foto_path in alunos:
        if os.path.exists(foto_path):
            alunos_validos.append((aluno_id, nome, foto_path))
        else:
            print(
                f"AVISO: foto não encontrada para {nome}: {foto_path}"
            )

    if not alunos_validos:
        print("Nenhuma foto de aluno está disponível.")
        return

    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        print("ERRO: não foi possível abrir a câmera.")
        return

    print("\n=== RECONHECIMENTO FACIAL ===")
    print("Olhe para a câmera.")
    print("Pressione ESC para sair.")

    contador = 0
    ultimo_resultado = "Procurando..."
    ultimo_aluno_id = None

    while True:
        ok, frame = camera.read()

        if not ok:
            print("ERRO: não foi possível ler a câmera.")
            break

        # Faz a comparação a cada 8 frames para diminuir o uso de CPU.
        contador += 1

        if contador % 8 == 0:
            encontrado = False

            for aluno_id, nome, foto_path in alunos_validos:
                try:
                    verificacao = DeepFace.verify(
                        img1_path=frame,
                        img2_path=foto_path,
                        model_name=MODELO,
                        detector_backend=DETECTOR,
                        enforce_detection=True,
                        align=True
                    )

                    if verificacao.get("verified", False):
                        ultimo_resultado = f"Reconhecido: {nome}"
                        ultimo_aluno_id = aluno_id
                        encontrado = True
                        break

                except Exception:
                    # Normalmente significa que nenhum rosto foi
                    # encontrado naquele frame.
                    continue

            if not encontrado:
                ultimo_resultado = "Rosto nao reconhecido"
                ultimo_aluno_id = None

        cv2.putText(
            frame,
            ultimo_resultado,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0) if ultimo_aluno_id else (0, 0, 255),
            2
        )

        cv2.putText(
            frame,
            "ESC = sair",
            (20, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2
        )

        cv2.imshow("Reconhecimento facial", frame)

        tecla = cv2.waitKey(1) & 0xFF

        if tecla == 27:
            break

        # Pressione ENTER para registrar a presença do reconhecido.
        if tecla == 13 and ultimo_aluno_id is not None:
            registrar_presenca(ultimo_aluno_id)

    camera.release()
    cv2.destroyAllWindows()


# ============================================================
# MENU
# ============================================================

def menu():
    preparar_banco()

    while True:
        print("\n==============================")
        print(" SISTEMA DE RECONHECIMENTO")
        print("==============================")
        print("1 - Cadastrar aluno")
        print("2 - Reconhecer aluno")
        print("3 - Sair")

        opcao = input("Escolha: ").strip()

        if opcao == "1":
            cadastrar_aluno()

        elif opcao == "2":
            reconhecer_alunos()

        elif opcao == "3":
            print("Encerrando...")
            break

        else:
            print("Opção inválida.")


if __name__ == "__main__":
    menu()
