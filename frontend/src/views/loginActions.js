export const createLoginActions = ({ auth, router, message, showLoginError }) => ({
  async submit({ initialized, username, password, loginApi }) {
    if (!initialized.value) {
      return {
        status: 'needs-init',
        onHandled() {
          showLoginError('系统未初始化，请先设置账号密码')
        }
      }
    }

    try {
      const { data } = await loginApi({
        username: username.value,
        password: password.value
      })
      auth.setAuth(data.username || username.value, data.access_token)
      auth.clearProject()
      message.success('登录成功')
      router.push('/projects')
      return { status: 'ok' }
    } catch (e) {
      if (e.response?.data?.detail === '系统未初始化，请先创建管理员账号') {
        return {
          status: 'needs-init',
          onHandled() {
            showLoginError('系统未初始化，请先设置账号密码')
          }
        }
      }
      showLoginError(e.response?.data?.detail || '登录失败')
      return { status: 'error' }
    }
  }
})
