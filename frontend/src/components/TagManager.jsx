import React, { useState } from 'react';

const PRESET_COLORS = [
  '#EF4444', // Red
  '#F97316', // Orange
  '#F59E0B', // Amber
  '#84CC16', // Lime
  '#10B981', // Emerald
  '#06B6D4', // Cyan
  '#3B82F6', // Blue
  '#6366F1', // Indigo
  '#8B5CF6', // Violet
  '#A855F7', // Purple
  '#EC4899', // Pink
  '#6B7280', // Gray
];

function TagManager({ tags, onTagsChange }) {
  const [newTagName, setNewTagName] = useState('');
  const [selectedColor, setSelectedColor] = useState('#3B82F6');
  const [editingTag, setEditingTag] = useState(null);
  const [editName, setEditName] = useState('');
  const [editColor, setEditColor] = useState('');

  const handleCreateTag = async (e) => {
    e.preventDefault();
    if (!newTagName.trim()) return;

    try {
      const response = await fetch('/api/tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newTagName.trim(),
          color: selectedColor
        })
      });

      if (response.ok) {
        setNewTagName('');
        onTagsChange();
      } else {
        const error = await response.json();
        alert(error.detail || 'Failed to create tag');
      }
    } catch (error) {
      console.error('Error creating tag:', error);
    }
  };

  const handleDeleteTag = async (tagId) => {
    if (!window.confirm('Are you sure you want to delete this tag? It will be removed from all channels.')) {
      return;
    }

    try {
      const response = await fetch(`/api/tags/${tagId}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        onTagsChange();
      }
    } catch (error) {
      console.error('Error deleting tag:', error);
    }
  };

  const startEditing = (tag) => {
    setEditingTag(tag);
    setEditName(tag.name);
    setEditColor(tag.color);
  };

  const handleUpdateTag = async (e) => {
    e.preventDefault();
    if (!editName.trim() || !editingTag) return;

    try {
      const response = await fetch(`/api/tags/${editingTag.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editName.trim(),
          color: editColor
        })
      });

      if (response.ok) {
        setEditingTag(null);
        onTagsChange();
      }
    } catch (error) {
      console.error('Error updating tag:', error);
    }
  };

  return (
    <div>
      <div className="card">
        <h2>Create New Tag</h2>
        <form onSubmit={handleCreateTag}>
          <div className="form-group">
            <label>Tag Name</label>
            <input
              type="text"
              value={newTagName}
              onChange={(e) => setNewTagName(e.target.value)}
              placeholder="e.g., Gaming, Work, Important"
              required
            />
          </div>
          
          <div className="form-group">
            <label>Color</label>
            <div className="color-picker">
              {PRESET_COLORS.map(color => (
                <div
                  key={color}
                  className={`color-option ${selectedColor === color ? 'selected' : ''}`}
                  style={{ backgroundColor: color }}
                  onClick={() => setSelectedColor(color)}
                />
              ))}
            </div>
          </div>
          
          <button type="submit" className="btn btn-primary">
            Create Tag
          </button>
        </form>
      </div>

      <div className="card">
        <h2>Existing Tags ({tags.length})</h2>
        
        {tags.length === 0 ? (
          <div className="empty-state">
            <p>No tags created yet. Create your first tag above!</p>
          </div>
        ) : (
          <div className="tag-list">
            {tags.map(tag => (
              <div
                key={tag.id}
                className="tag-item"
                style={{ backgroundColor: tag.color, color: 'white' }}
              >
                <span>{tag.name}</span>
                <div className="tag-actions">
                  <button onClick={() => startEditing(tag)} title="Edit">
                    ✎
                  </button>
                  <button onClick={() => handleDeleteTag(tag.id)} title="Delete">
                    ×
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {editingTag && (
        <div className="modal-overlay" onClick={() => setEditingTag(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>Edit Tag</h3>
            <form onSubmit={handleUpdateTag}>
              <div className="form-group">
                <label>Tag Name</label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  required
                />
              </div>
              
              <div className="form-group">
                <label>Color</label>
                <div className="color-picker">
                  {PRESET_COLORS.map(color => (
                    <div
                      key={color}
                      className={`color-option ${editColor === color ? 'selected' : ''}`}
                      style={{ backgroundColor: color }}
                      onClick={() => setEditColor(color)}
                    />
                  ))}
                </div>
              </div>
              
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setEditingTag(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default TagManager;
