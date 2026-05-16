import ollama

def consultar_modelo(mensaje_usuario):
   
    print(" Procesando a TARS localmente...")
    
    try:
        respuesta = ollama.chat(
            model='phi3', 
            messages=[
                {
                    'role': 'user',
                    'content': mensaje_usuario
                }
            ]
        )
        return respuesta['message']['content']
        
    except Exception as e:
        return f"ERROR al conectar con el modelo local: {e}"

if __name__ == "__main__":
    prompt = "¿como resolver fibonacci en c++?"
    resultado = consultar_modelo(prompt)
    
    print("\n Respuesta del modelo:\n")
    print(resultado)