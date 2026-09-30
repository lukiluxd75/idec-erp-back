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
                $pythonExe = "C:\\Program Files\\Python311\\python.exe"

                Write-Host "Usando Python en: $pythonExe"
                & "$pythonExe" -m pip install --upgrade pip

                if (Test-Path "requirements.txt") {
                    Write-Host "Instalando dependencias desde requirements.txt..."
                    & "$pythonExe" -m pip install -r requirements.txt
                } else {
                    Write-Host "ADVERTENCIA: No se encontró requirements.txt"
                }
                '''
            }
        }
        
        stage('Pruebas y Verificación') {
            steps {
                powershell '''
                $ErrorActionPreference = "Stop"
                $env:PYTHONIOENCODING = "utf-8"
                $env:PYTHONPATH = "$PWD"
                $pythonExe = "C:\\Program Files\\Python311\\python.exe"
                
                Write-Host "Verificando importación del módulo app.main..."
                & "$pythonExe" -X utf8 -c "import app.main; print('¡La app del backend cargo con exito!')"
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
                
                $process = Start-Process robocopy -ArgumentList "`"$PWD`" `"$targetDir`" /MIR /XD .git .venv __pycache__ /XF Jenkinsfile /R:2 /W:1 /NJH /NJS" -Wait -NoNewWindow -PassThru
                
                if ($process.ExitCode -le 7) {
                    Write-Host "Despliegue a IIS completado con éxito."
                    exit 0
                } else {
                    Write-Error "Error en Robocopy al copiar a IIS. Código de salida: $($process.ExitCode)"
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
            echo 'El pipeline del Backend ha fallado. Revisa la consola.'
        }
    }
}