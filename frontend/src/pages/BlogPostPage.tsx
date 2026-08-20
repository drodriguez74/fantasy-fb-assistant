import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import {
  ArrowLeftIcon,
  CalendarIcon,
  UserIcon,
  TagIcon,
  ClockIcon,
  ExclamationTriangleIcon
} from '@heroicons/react/24/outline'

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
  tags: any
}

export function BlogPostPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [blogPost, setBlogPost] = useState<BlogPost | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (id) {
      loadBlogPost(parseInt(id))
    }
  }, [id])

  const loadBlogPost = async (postId: number) => {
    try {
      setLoading(true)
      const response = await api.get(`/content/blog-posts/${postId}`)
      setBlogPost(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load blog post')
    } finally {
      setLoading(false)
    }
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      waiver_wire: 'bg-green-100 text-green-800',
      weekly_rankings: 'bg-blue-100 text-blue-800',
      player_analysis: 'bg-purple-100 text-purple-800',
      injury_report: 'bg-red-100 text-red-800',
      start_sit: 'bg-yellow-100 text-yellow-800',
      breakout_candidates: 'bg-orange-100 text-orange-800',
      draft_strategy: 'bg-indigo-100 text-indigo-800'
    }
    return colors[category] || 'bg-gray-100 text-gray-800'
  }

  const getCategoryName = (category: string) => {
    const names: Record<string, string> = {
      waiver_wire: 'Waiver Wire',
      weekly_rankings: 'Rankings',
      player_analysis: 'Player Analysis',
      injury_report: 'Injury Report',
      start_sit: 'Start/Sit',
      breakout_candidates: 'Breakouts',
      draft_strategy: 'Draft Strategy'
    }
    return names[category] || category.replace('_', ' ')
  }


  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-2 text-gray-600">Loading article...</span>
      </div>
    )
  }

  if (error || !blogPost) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex">
            <ExclamationTriangleIcon className="h-5 w-5 text-red-400" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <div className="mt-2 text-sm text-red-700">
                {error || 'Blog post not found'}
              </div>
            </div>
          </div>
        </div>
        <button
          onClick={() => navigate('/blog')}
          className="mt-4 flex items-center text-blue-600 hover:text-blue-700"
        >
          <ArrowLeftIcon className="h-4 w-4 mr-1" />
          Back to Blog
        </button>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* Back Button */}
      <button
        onClick={() => navigate('/blog')}
        className="mb-6 flex items-center text-blue-600 hover:text-blue-700 transition-colors"
      >
        <ArrowLeftIcon className="h-4 w-4 mr-1" />
        Back to Blog
      </button>

      {/* Article Header */}
      <article className="bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden">
        <div className="p-8">
          {/* Category and Status */}
          <div className="flex items-center justify-between mb-4">
            <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getCategoryColor(blogPost.category)}`}>
              <TagIcon className="h-4 w-4 mr-1" />
              {getCategoryName(blogPost.category)}
            </span>
            
            <div className="flex items-center space-x-4">
              {blogPost.featured && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                  ⭐ Featured
                </span>
              )}
              {!blogPost.is_published && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                  Draft
                </span>
              )}
            </div>
          </div>

          {/* Title */}
          <h1 className="text-4xl font-bold text-gray-900 mb-6 leading-tight">
            {blogPost.title}
          </h1>

          {/* Meta Information */}
          <div className="flex items-center space-x-6 text-sm text-gray-500 mb-8 border-b border-gray-200 pb-6">
            <div className="flex items-center">
              <UserIcon className="h-4 w-4 mr-1" />
              <span>{blogPost.author}</span>
            </div>
            <div className="flex items-center">
              <CalendarIcon className="h-4 w-4 mr-1" />
              <span>{formatDate(blogPost.created_at)}</span>
            </div>
            {blogPost.updated_at && blogPost.updated_at !== blogPost.created_at && (
              <div className="flex items-center">
                <ClockIcon className="h-4 w-4 mr-1" />
                <span>Updated {formatDate(blogPost.updated_at)}</span>
              </div>
            )}
          </div>

          {/* Content */}
          <div className="prose prose-lg max-w-none">
            <div 
              className="text-gray-700 leading-relaxed whitespace-pre-wrap"
              style={{ lineHeight: '1.8' }}
            >
              {blogPost.content}
            </div>
          </div>

          {/* Tags */}
          {blogPost.tags && typeof blogPost.tags === 'object' && Object.keys(blogPost.tags).length > 0 && (
            <div className="mt-8 pt-6 border-t border-gray-200">
              <h3 className="text-sm font-medium text-gray-900 mb-3">Tags & Metadata</h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(blogPost.tags).map(([key, value]) => (
                  <span
                    key={key}
                    className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                  >
                    {key}: {String(value)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </article>

      {/* Navigation */}
      <div className="mt-8 text-center">
        <button
          onClick={() => navigate('/blog')}
          className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 transition-colors"
        >
          Back to All Articles
        </button>
      </div>
    </div>
  )
}