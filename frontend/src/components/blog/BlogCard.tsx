import { useNavigate } from 'react-router-dom'
import { ClockIcon, TagIcon, UserIcon } from '@heroicons/react/24/outline'
import { BlogPost } from '../../types'

interface BlogCardProps {
  post: BlogPost
  onDelete?: (id: number) => void
  showActions?: boolean
}

export function BlogCard({ post, onDelete, showActions = false }: BlogCardProps) {
  const navigate = useNavigate()

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffTime = Math.abs(now.getTime() - date.getTime())
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))
    
    if (diffDays === 1) return '1 day ago'
    if (diffDays < 7) return `${diffDays} days ago`
    return date.toLocaleDateString()
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

  return (
    <article className="bg-white rounded-lg shadow border border-gray-200 p-6 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-3">
        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getCategoryColor(post.category || '')}`}>
          <TagIcon className="h-3 w-3 mr-1" />
          {getCategoryName(post.category || '')}
        </span>
        <div className="flex items-center text-sm text-gray-500">
          <ClockIcon className="h-4 w-4 mr-1" />
          {formatDate(post.created_at)}
        </div>
      </div>
      
      <h2 className="text-xl font-semibold mb-3 text-gray-900 line-clamp-2">
        {post.title}
      </h2>
      
      <p className="text-gray-600 mb-4 line-clamp-3">
        {post.summary || post.content.replace(/#{1,6}\s/g, '').substring(0, 150)}...
      </p>
      
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4 text-xs text-gray-500">
          <div className="flex items-center">
            <UserIcon className="h-3 w-3 mr-1" />
            AI Assistant
          </div>
          {post.perspectives_count && (
            <div className="flex items-center">
              <span>Perspectives: {post.perspectives_count}</span>
            </div>
          )}
          {post.consensus_score && (
            <div className="flex items-center">
              <span className="text-green-600 font-medium">
                Score: {post.consensus_score.toFixed(1)}/10
              </span>
            </div>
          )}
        </div>
        
        <div className="flex items-center space-x-2">
          <button 
            onClick={() => navigate(`/blog/${post.id}`)}
            className="text-blue-600 hover:text-blue-700 text-sm font-medium transition-colors"
          >
            Read More →
          </button>
          
          {showActions && onDelete && (
            <button
              onClick={() => onDelete(post.id)}
              className="text-red-600 hover:text-red-700 text-sm font-medium transition-colors"
            >
              Delete
            </button>
          )}
        </div>
      </div>
      
      {post.featured && (
        <div className="mt-3 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
          ⭐ Featured
        </div>
      )}
    </article>
  )
}