// devflow 流水线（Jenkins Declarative Pipeline）
// 由 `devflow ci emit --platform jenkins` 生成。
// 依赖：Jenkins 2.332+、Python 3.8+（ agent 上可用 {{PYTHON}} ）

pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    environment {
        DEVFLOW_ENTRY = '{{ENTRY}}'
        DEVFLOW_PY    = '{{PYTHON}}'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Sync Artifacts') {
            steps {
                sh '${DEVFLOW_PY} "${DEVFLOW_ENTRY}" sync'
            }
        }

        stage('Gate') {
            steps {
                sh '''
                    set -o pipefail
                    ${DEVFLOW_PY} "${DEVFLOW_ENTRY}" check --json > devflow-check.json || true
                    cat devflow-check.json
                '''
                sh '${DEVFLOW_PY} "${DEVFLOW_ENTRY}" gate'
            }
            post {
                always {
                    archiveArtifacts artifacts: 'devflow-check.json', allowEmptyArchive: true
                }
            }
        }

        stage('Record') {
            steps {
                script {
                    def result = currentBuild.currentResult == 'SUCCESS' ? 'success' : 'failed'
                    sh """
                        ${DEVFLOW_PY} "${DEVFLOW_ENTRY}" ci record --result ${result} --run-id "${env.BUILD_NUMBER}" --set commit="${env.GIT_COMMIT}"
                    """
                }
            }
        }

        stage('Release Gate') {
            when {
                buildingTag()
            }
            steps {
                sh '${DEVFLOW_PY} "${DEVFLOW_ENTRY}" gate --phase release --mode strict'
            }
        }
    }

    post {
        always {
            echo "devflow 状态快照：{{STATE_DIR}}/STATUS.md"
        }
        failure {
            echo '门禁未通过，请按 devflow-check.json 中的 hint 修复后重新构建'
        }
    }
}
