import { useState, useEffect } from 'react'
import { useAuth } from '../hooks/useAuth'
import { api } from '../services/api'
import {
  PlusIcon,
  DocumentTextIcon,
  EyeIcon,
  TrashIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon
} from '@heroicons/react/24/outline'

interface ContentTemplate {
  name: string
  description: string
  parameters: Record<string, any>
}

interface ContentGenerationRequest {
  content_type: string
  topic: string
  parameters: Record<string, any>
}

interface BlogPost {
  id: number
  title: string
  content: string
  author: string
  category: string
  is_published: boolean
  featured: boolean
  created_at: string
  updated_at?: string
  tags: Record<string, any>
}

export function ContentPage() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<'generate' | 'manage'>('generate')
  const [templates, setTemplates] = useState<Record<string, ContentTemplate>>({})
  const [blogPosts, setBlogPosts] = useState<BlogPost[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const [selectedTemplate, setSelectedTemplate] = useState<string>('')
  const [generationParams, setGenerationParams] = useState<Record<string, any>>({})
  const [customTopic, setCustomTopic] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    if (user) {
      loadTemplates()
      loadBlogPosts()
    }
  }, [user])

  const loadTemplates = async () => {
    try {
      const response = await api.get('/content/templates')
      setTemplates(response.data.templates)
    } catch (err) {
      setError('Failed to load content templates')
    }
  }

  const loadBlogPosts = async () => {
    try {
      setLoading(true)
      const response = await api.get('/content/blog-posts/?limit=20&published_only=false')
      setBlogPosts(response.data.blog_posts)
    } catch (err) {
      setError('Failed to load blog posts')
    } finally {
      setLoading(false)
    }
  }

  const handleGenerate = async () => {
    if (!selectedTemplate || !customTopic) {
      setError('Please select a template and provide a topic')
      return
    }

    try {
      setIsGenerating(true)
      setError('')
      
      const request: ContentGenerationRequest = {
        content_type: selectedTemplate,
        topic: customTopic,
        parameters: generationParams
      }

      const response = await api.post('/content/generate-and-save', request)
      
      if (response.data.content_generated && response.data.content_saved) {
        setSuccess(`Content generated and saved successfully! Blog post ID: ${response.data.blog_post_id}`)
        setCustomTopic('')
        setGenerationParams({})
        setSelectedTemplate('')
        await loadBlogPosts() // Reload blog posts
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate content')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleQuickGenerate = async (type: 'weekly_rankings' | 'waiver_wire' | 'injury_report', params: any = {}) => {
    try {
      setIsGenerating(true)
      setError('')
      
      let response
      if (type === 'weekly_rankings') {
        response = await api.post(`/content/weekly-rankings?week=${params.week || 1}&position=${params.position || 'ALL'}&save_as_post=true`)
      } else if (type === 'waiver_wire') {
        response = await api.post(`/content/waiver-wire?week=${params.week || 1}&save_as_post=true`)
      } else if (type === 'injury_report') {
        response = await api.post('/content/injury-report?save_as_post=true')
      }
      
      if (response?.data) {
        setSuccess(`${type.replace('_', ' ')} content generated successfully!`)
        await loadBlogPosts()
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || `Failed to generate ${type}`)
    } finally {
      setIsGenerating(false)
    }
  }

  const handlePublishToggle = async (postId: number, isPublished: boolean) => {
    try {
      await api.put(`/content/blog-posts/${postId}/publish`, {
        blog_post_id: postId,
        is_published: !isPublished,
        featured: false
      })
      setSuccess(`Post ${!isPublished ? 'published' : 'unpublished'} successfully`)
      await loadBlogPosts()
    } catch (err) {
      setError('Failed to update post status')
    }
  }

  const handleDelete = async (postId: number) => {
    if (!confirm('Are you sure you want to delete this post?')) return
    
    try {
      await api.delete(`/content/blog-posts/${postId}`)
      setSuccess('Post deleted successfully')
      await loadBlogPosts()
    } catch (err) {
      setError('Failed to delete post')
    }
  }

  const renderParameterInput = (paramName: string, paramConfig: any) => {
    const value = generationParams[paramName] || paramConfig.default || ''
    
    return (
      <div key={paramName} className="space-y-1">
        <label className="block text-sm font-medium text-gray-700">
          {paramName.charAt(0).toUpperCase() + paramName.slice(1).replace('_', ' ')}
        </label>
        <p className="text-xs text-gray-500">{paramConfig.description}</p>
        <input
          type={paramConfig.type === 'integer' ? 'number' : 'text'}
          value={value}
          onChange={(e) => setGenerationParams(prev => ({
            ...prev,
            [paramName]: paramConfig.type === 'integer' ? parseInt(e.target.value) || 0 : e.target.value
          }))}
          className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
          placeholder={paramConfig.default?.toString() || ''}
        />
      </div>
    )
  }

  if (!user) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="text-center">
          <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">Authentication Required</h3>
          <p className="mt-1 text-sm text-gray-500">Please sign in to access content generation features.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="border-b border-gray-200 mb-6">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('generate')}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'generate'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Generate Content
            </button>
            <button
              onClick={() => setActiveTab('manage')}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'manage'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Manage Content
            </button>
          </nav>
        </div>

        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 rounded-md p-4">
            <div className="flex">
              <ExclamationTriangleIcon className="h-5 w-5 text-red-400" />
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">Error</h3>
                <div className="mt-2 text-sm text-red-700">{error}</div>
              </div>
            </div>
          </div>
        )}

        {success && (
          <div className="mb-4 bg-green-50 border border-green-200 rounded-md p-4">
            <div className="flex">
              <CheckCircleIcon className="h-5 w-5 text-green-400" />
              <div className="ml-3">
                <h3 className="text-sm font-medium text-green-800">Success</h3>
                <div className="mt-2 text-sm text-green-700">{success}</div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'generate' && (
          <div className="space-y-8">
            {/* Quick Generation Section */}
            <div className="bg-white shadow rounded-lg p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Quick Generation</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <button
                  onClick={() => handleQuickGenerate('weekly_rankings', { week: 1, position: 'ALL' })}
                  disabled={isGenerating}
                  className="p-4 border-2 border-dashed border-gray-300 rounded-lg hover:border-blue-500 hover:bg-blue-50 transition-colors disabled:opacity-50"
                >
                  <DocumentTextIcon className="h-8 w-8 text-blue-600 mx-auto mb-2" />
                  <div className="text-sm font-medium text-gray-900">Weekly Rankings</div>
                  <div className="text-xs text-gray-500">Generate current week rankings</div>
                </button>
                
                <button
                  onClick={() => handleQuickGenerate('waiver_wire', { week: 1 })}
                  disabled={isGenerating}
                  className="p-4 border-2 border-dashed border-gray-300 rounded-lg hover:border-blue-500 hover:bg-blue-50 transition-colors disabled:opacity-50"
                >
                  <PlusIcon className="h-8 w-8 text-green-600 mx-auto mb-2" />
                  <div className="text-sm font-medium text-gray-900">Waiver Wire</div>
                  <div className="text-xs text-gray-500">Generate waiver targets</div>
                </button>
                
                <button
                  onClick={() => handleQuickGenerate('injury_report')}
                  disabled={isGenerating}
                  className="p-4 border-2 border-dashed border-gray-300 rounded-lg hover:border-blue-500 hover:bg-blue-50 transition-colors disabled:opacity-50"
                >
                  <ExclamationTriangleIcon className="h-8 w-8 text-red-600 mx-auto mb-2" />
                  <div className="text-sm font-medium text-gray-900">Injury Report</div>
                  <div className="text-xs text-gray-500">Generate injury analysis</div>
                </button>
              </div>
            </div>

            {/* Custom Generation Section */}
            <div className="bg-white shadow rounded-lg p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Custom Content Generation</h3>
              
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Content Template
                  </label>
                  <select
                    value={selectedTemplate}
                    onChange={(e) => {
                      setSelectedTemplate(e.target.value)
                      setGenerationParams({})
                    }}
                    className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                  >
                    <option value="">Select a template...</option>
                    {Object.entries(templates).map(([key, template]) => (
                      <option key={key} value={key}>
                        {template.name}
                      </option>
                    ))}
                  </select>
                  {selectedTemplate && templates[selectedTemplate] && (
                    <p className="mt-1 text-sm text-gray-500">
                      {templates[selectedTemplate].description}
                    </p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Topic
                  </label>
                  <input
                    type="text"
                    value={customTopic}
                    onChange={(e) => setCustomTopic(e.target.value)}
                    className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                    placeholder="Enter content topic..."
                  />
                </div>

                {selectedTemplate && templates[selectedTemplate] && (
                  <div className="space-y-4">
                    <h4 className="text-sm font-medium text-gray-900">Parameters</h4>
                    {Object.entries(templates[selectedTemplate].parameters).map(([paramName, paramConfig]) =>
                      renderParameterInput(paramName, paramConfig)
                    )}
                  </div>
                )}

                <button
                  onClick={handleGenerate}
                  disabled={isGenerating || !selectedTemplate || !customTopic}
                  className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isGenerating ? (
                    <>
                      <ClockIcon className="animate-spin -ml-1 mr-3 h-5 w-5" />
                      Generating...
                    </>
                  ) : (
                    'Generate Content'
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'manage' && (
          <div className="bg-white shadow rounded-lg">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-medium text-gray-900">Generated Content</h3>
            </div>
            
            {loading ? (
              <div className="p-6 text-center">
                <ClockIcon className="animate-spin h-8 w-8 text-gray-400 mx-auto mb-2" />
                <p className="text-sm text-gray-500">Loading blog posts...</p>
              </div>
            ) : blogPosts.length === 0 ? (
              <div className="p-6 text-center">
                <DocumentTextIcon className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-sm font-medium text-gray-900">No content generated yet</h3>
                <p className="text-sm text-gray-500">Generate some content to see it listed here.</p>
              </div>
            ) : (
              <div className="divide-y divide-gray-200">
                {blogPosts.map((post) => (
                  <div key={post.id} className="p-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <h4 className="text-lg font-medium text-gray-900">{post.title}</h4>
                        <div className="mt-1 flex items-center space-x-4 text-sm text-gray-500">
                          <span>By {post.author}</span>
                          <span>•</span>
                          <span>{post.category}</span>
                          <span>•</span>
                          <span>{new Date(post.created_at).toLocaleDateString()}</span>
                        </div>
                        <p className="mt-2 text-sm text-gray-600 line-clamp-2">
                          {post.content.substring(0, 200)}...
                        </p>
                      </div>
                      
                      <div className="flex items-center space-x-2">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          post.is_published 
                            ? 'bg-green-100 text-green-800' 
                            : 'bg-yellow-100 text-yellow-800'
                        }`}>
                          {post.is_published ? 'Published' : 'Draft'}
                        </span>
                        
                        <button
                          onClick={() => handlePublishToggle(post.id, post.is_published)}
                          className="p-2 text-gray-400 hover:text-gray-600"
                          title={post.is_published ? 'Unpublish' : 'Publish'}
                        >
                          <EyeIcon className="h-5 w-5" />
                        </button>
                        
                        <button
                          onClick={() => handleDelete(post.id)}
                          className="p-2 text-gray-400 hover:text-red-600"
                          title="Delete"
                        >
                          <TrashIcon className="h-5 w-5" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}