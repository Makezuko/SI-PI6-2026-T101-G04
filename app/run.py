from app import app

if __name__ == "__main__":
    # A observação por eventos pode perder alterações em pastas do OneDrive.
    # O modo stat verifica os arquivos e mantém Python e templates sincronizados.
    app.run(debug=True, reloader_type='stat')
