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
                Write-Host "Actualizando pip e instalando dependencias..."
                & "C:\\Program Files\\Python311\\python.exe" -m pip install --upgrade pip
                
                if (Test-Path "requirements.txt") {
                    & "C:\\Program Files\\Python311\\python.exe" -m pip install -r requirements.txt
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
                
                Write-Host "Verificando carga del módulo app.main..."
                & "C:\\Program Files\\Python311\\python.exe" -X utf8 -c "import app.main; print('¡La app del backend cargo con exito!')"
                '''
            }
        }
        
        stage('Desplegar a IIS') {
            steps {
                powershell '''
                $ErrorActionPreference = "Stop"
                $targetDir = "C:\\inetpub\\wwwroot\\siscatJenkins"
                
                Write-Host "Copiando archivos a IIS en $targetDir..."
                if (-not (Test-Path $targetDir)) {
                    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
                }
                
                robocopy "$PWD" "$targetDir" /MIR /XD .git .venv __pycache__ /XF Jenkinsfile /R:2 /W:1 /NJH /NJS
                
                if ($LASTEXITCODE -le 7) {
                    $global:LASTEXITCODE = 0
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