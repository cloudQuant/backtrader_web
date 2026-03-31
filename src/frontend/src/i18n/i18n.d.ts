import type { DefineLocaleMessage } from 'vue-i18n'

declare module 'vue-i18n' {
  export interface DefineLocaleMessage {
    common: {
      loading: string
      success: string
      failed: string
      confirm: string
      cancel: string
      save: string
      delete: string
      edit: string
      add: string
      search: string
      reset: string
      submit: string
      back: string
      detail: string
      status: string
      action: string
      noData: string
      all: string
      enable: string
      disable: string
      yes: string
      no: string
    }
    nav: {
      dashboard: string
      strategy: string
      backtest: string
      optimization: string
      liveTrading: string
      paperTrading: string
      data: string
      settings: string
      comparison: string
    }
    auth: {
      login: string
      logout: string
      register: string
      username: string
      password: string
      confirmPassword: string
      email: string
      rememberMe: string
      forgotPassword: string
      loginSuccess: string
      logoutSuccess: string
      registerSuccess: string
      invalidCredentials: string
      sessionExpired: string
    }
    backtest: {
      title: string
      runBacktest: string
      selectStrategy: string
      selectSymbol: string
      dateRange: string
      startDate: string
      endDate: string
      initialCash: string
      parameters: string
      results: string
      totalReturn: string
      annualReturn: string
      maxDrawdown: string
      sharpeRatio: string
      winRate: string
      profitLossRatio: string
      trades: string
      equityCurve: string
      dailyPnL: string
      positionAnalysis: string
      taskStatus: string
      pending: string
      running: string
      completed: string
      failed: string
      viewDetail: string
      downloadReport: string
    }
    strategy: {
      title: string
      createStrategy: string
      editStrategy: string
      deleteStrategy: string
      strategyName: string
      strategyType: string
      strategyCode: string
      description: string
      templates: string
      myStrategies: string
      uploadStrategy: string
      version: string
      createdAt: string
      updatedAt: string
      confirmDelete: string
    }
    liveTrading: {
      title: string
      createInstance: string
      instanceList: string
      instanceName: string
      broker: string
      account: string
      status: string
      start: string
      stop: string
      pause: string
      resume: string
      positions: string
      orders: string
      trades: string
      balance: string
      pnl: string
      dailyPnL: string
      riskControl: string
      alerts: string
      logs: string
      connected: string
      disconnected: string
      connecting: string
      error: string
    }
    optimization: {
      title: string
      createTask: string
      taskList: string
      parameterRange: string
      optimizationMethod: string
      objectiveFunction: string
      results: string
      bestParams: string
      paramChart: string
      inProgress: string
      completed: string
      failed: string
    }
    data: {
      title: string
      uploadData: string
      dataList: string
      dataType: string
      symbol: string
      date: string
      open: string
      high: string
      low: string
      close: string
      volume: string
      openInterest: string
      importSuccess: string
      importFailed: string
    }
    settings: {
      title: string
      general: string
      security: string
      notification: string
      language: string
      theme: string
      light: string
      dark: string
      auto: string
    }
    errors: {
      networkError: string
      serverError: string
      notFound: string
      unauthorized: string
      forbidden: string
      validationError: string
      unknownError: string
    }
    messages: {
      confirmDelete: string
      saveSuccess: string
      saveFailed: string
      deleteSuccess: string
      deleteFailed: string
      copySuccess: string
      copyFailed: string
    }
  }
}

export default DefineLocaleMessage
