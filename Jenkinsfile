pipeline {
    agent {
        label 'windows-runner'
    }
    parameters {
        booleanParam(name: 'EJECUTAR_AUTOMATICO', defaultValue: true, description: 'Ejecución fluida automática')
    }
    triggers {
        cron('30 2 * * *')
    }
    stages {
        stage('Preparación') {
            steps {
                cleanWs()
                checkout scm
            }
        }
        
        stage('Instalar Dependencias') {
            steps {
                powershell '''
                $ErrorActionPreference = "Stop"
                
                # Buscar ejecutable de Python dinámicamente si no está en la ruta por defecto
                $pythonPath = "C:\\Program Files\\Python311\\python.exe"
                if (-not (Test-Path $pythonPath)) {$pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
                }
                
                if (-not $pythonPath) {
                    Write-Error "No se encontró el ejecutable de Python en el servidor."
                    exit 1
                }
                
                Write-Host "Usando Python en: $pythonPath"
                & "$pythonPath" -m pip install --upgrade pip
                
                if (Test-Path "requirements.txt") {
                    Write-Host "Instalando dependencias desde requirements.txt..."
                    & "$pythonPath" -m pip install -r requirements.txt
                } else {
                    Write-Host "ADVERTENCIA: No se encontró requirements.txt"
                }
                '''
            }
        }
        
        stage('Pruebas y Verificación') {
            steps {
                powershell '''
                $env:PYTHONIOENCODING = "utf-8"
                $env:PYTHONPATH = "$PWD"
                
                $pythonPath = "C:\\Program Files\\Python311\\python.exe"
                if (-not (Test-Path $pythonPath)) {$pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
                }
                
                Write-Host "Verificando la app..."
                & "$pythonPath" -X utf8 -c "import app.main; print('¡La app del backend cargo con exito!')"
                
                if ($LASTEXITCODE -ne 0) {
                    Write-Error "Fallo la importacion del modulo app.main. Verifique si faltan dependencias o variables de entorno."
                    exit $LASTEXITCODE
                }
                '''
            }
        }
        
        stage('Desplegar a IIS') {
            steps {
                powershell '''
                $targetDir = "C:\\inetpub\\wwwroot\\siscatJenkins"
                
                Write-Host "Copiando archivos a IIS en $targetDir..."
                if (-not (Test-Path $targetDir)) {
                    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
                }
                
                # Ejecución aislada de Robocopy para evitar falso positivo en Jenkins
                $process = Start-Process robocopy -ArgumentList "`"$PWD`" `"$targetDir`" /MIR /XD .git .venv __pycache__ /XF Jenkinsfile /R:2 /W:1 /NJH /NJS" -Wait -NoNewWindow -PassThru
                
                if ($process.ExitCode -le 7) {
                    Write-Host "Despliegue a IIS completado con exito (Codigo Robocopy: $($process.ExitCode))."
                    exit 0
                } else {
                    Write-Error "Error grave en Robocopy. Codigo de salida: $($process.ExitCode)"
                    exit $process.ExitCode
                }
                '''
            }
        }
    }
    post {
        success {
            echo '¡El pipeline del Backend se ejecutó y desplegó con éxito!'
        }
        failure {
            echo 'El pipeline del Backend ha fallado. Revise la consola para identificar la etapa con error.'
        }
    }
}