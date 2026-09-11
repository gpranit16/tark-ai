import React, { useState } from 'react';
import { Plus, Tag, X } from 'lucide-react';
import clsx from 'clsx';

export default function CategoryPills({
  categories = [],
  selectedCategoryId,
  onSelectCategory,
  onCreateCategory,
  onDeleteCategory,
}) {
  const [isAdding, setIsAdding] = useState(false);
  const [newCatName, setNewCatName] = useState('');

  const handleCreate = async (e) => {
    e.preventDefault();
    if (newCatName.trim()) {
      await onCreateCategory({ name: newCatName.trim() });
      setNewCatName('');
      setIsAdding(false);
    }
  };

  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs scrollbar-none">
      <button
        onClick={() => onSelectCategory(null)}
        className={clsx(
          'px-3 py-1.5 rounded-lg font-medium transition-all duration-150 flex items-center gap-1.5 whitespace-nowrap',
          selectedCategoryId === null
            ? 'bg-accent/15 text-accent border border-accent/30 shadow-[0_0_12px_rgba(214,181,106,0.15)]'
            : 'bg-[#121215] hover:bg-[#18181D] text-[#8E8B85] hover:text-[#EDE8DF] border border-white/[0.05]'
        )}
      >
        <Tag size={12} />
        <span>All Categories</span>
      </button>

      {categories.map((cat) => {
        const isSelected = selectedCategoryId === cat.id;
        return (
          <div
            key={cat.id}
            className={clsx(
              'group px-3 py-1.5 rounded-lg font-medium transition-all duration-150 flex items-center gap-2 whitespace-nowrap cursor-pointer',
              isSelected
                ? 'bg-accent/15 text-accent border border-accent/30 shadow-[0_0_12px_rgba(214,181,106,0.15)]'
                : 'bg-[#121215] hover:bg-[#18181D] text-[#8E8B85] hover:text-[#EDE8DF] border border-white/[0.05]'
            )}
            onClick={() => onSelectCategory(isSelected ? null : cat.id)}
          >
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: cat.color || '#D6B56A' }}
            />
            <span>{cat.name}</span>
          </div>
        );
      })}

      {isAdding ? (
        <form onSubmit={handleCreate} className="flex items-center gap-1">
          <input
            type="text"
            placeholder="Category name"
            value={newCatName}
            autoFocus
            onChange={(e) => setNewCatName(e.target.value)}
            className="px-2.5 py-1 bg-[#121215] border border-accent/40 rounded-lg text-xs text-[#EDE8DF] focus:outline-none w-28"
          />
          <button
            type="submit"
            className="p-1 text-accent hover:bg-accent/10 rounded transition-colors"
          >
            <Plus size={14} />
          </button>
          <button
            type="button"
            onClick={() => setIsAdding(false)}
            className="p-1 text-[#777] hover:text-white rounded transition-colors"
          >
            <X size={14} />
          </button>
        </form>
      ) : (
        <button
          onClick={() => setIsAdding(true)}
          className="px-2.5 py-1.5 rounded-lg bg-[#121215] hover:bg-[#18181D] text-[#767682] hover:text-accent border border-dashed border-white/[0.08] hover:border-accent/30 text-xs flex items-center gap-1 transition-all whitespace-nowrap"
        >
          <Plus size={12} />
          <span>New Category</span>
        </button>
      )}
    </div>
  );
}
