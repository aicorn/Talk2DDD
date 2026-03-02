export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <div className="text-center">
        <h1 className="text-5xl font-bold text-blue-600 mb-4">
          🎯 Talk2DDD
        </h1>
        <p className="text-2xl text-gray-600 mb-8">
          AI 智能文档助手
        </p>
        <p className="text-lg text-gray-500 mb-12 max-w-2xl">
          通过对话方式，轻松创建和管理领域驱动设计（DDD）文档。
          让 AI 帮助你理解业务需求，生成技术文档。
        </p>
        <div className="flex gap-4 justify-center">
          <a
            href="/login"
            className="px-8 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
          >
            开始使用
          </a>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="px-8 py-3 border border-blue-600 text-blue-600 rounded-lg hover:bg-blue-50 transition-colors font-medium"
          >
            API 文档
          </a>
        </div>
        <div className="mt-16 grid grid-cols-3 gap-8 text-left max-w-3xl">
          <div className="p-6 bg-blue-50 rounded-lg">
            <h3 className="text-lg font-semibold text-blue-800 mb-2">💬 对话驱动</h3>
            <p className="text-blue-600 text-sm">通过自然语言对话，AI 帮助您梳理业务需求和领域知识</p>
          </div>
          <div className="p-6 bg-green-50 rounded-lg">
            <h3 className="text-lg font-semibold text-green-800 mb-2">📄 智能生成</h3>
            <p className="text-green-600 text-sm">自动生成 DDD 领域模型、用例文档和技术架构设计</p>
          </div>
          <div className="p-6 bg-purple-50 rounded-lg">
            <h3 className="text-lg font-semibold text-purple-800 mb-2">🔄 版本管理</h3>
            <p className="text-purple-600 text-sm">完整的文档版本历史，支持多人协作和变更追踪</p>
          </div>
        </div>
      </div>
    </main>
  )
}
