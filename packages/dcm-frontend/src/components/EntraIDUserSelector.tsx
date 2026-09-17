/**
 * EntraIDUserSelector - Component for searching and selecting users from EntraID
 * 
 * This component allows administrators to search for users in the corporate
 * EntraID directory and select them to add to DCM.
 */

import React, { useState, useCallback, useEffect } from 'react';
import { Search, User, Mail, Briefcase, Loader2 } from 'lucide-react';
import { searchEntraIDUsers, type EntraIDUserSearchParams } from '../api/dcmApiClient';
import type { EntraIDUser } from '../types/api';
import { Input } from './ui/input';

interface EntraIDUserSelectorProps {
  onSelectUser: (user: EntraIDUser) => void;
  placeholder?: string;
  className?: string;
}

interface SearchState {
  query: string;
  results: EntraIDUser[];
  isLoading: boolean;
  error: string | null;
  hasSearched: boolean;
}

export const EntraIDUserSelector: React.FC<EntraIDUserSelectorProps> = ({
  onSelectUser,
  placeholder = 'Rechercher un utilisateur (nom, email)...',
  className = '',
}) => {
  const [state, setState] = useState<SearchState>({
    query: '',
    results: [],
    isLoading: false,
    error: null,
    hasSearched: false,
  });

  const [searchTimeout, setSearchTimeout] = useState<number | null>(null);

  const performSearch = useCallback(async (query: string) => {
    if (query.length < 2) {
      setState(prev => ({
        ...prev,
        results: [],
        error: null,
        hasSearched: false,
      }));
      return;
    }

    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const params: EntraIDUserSearchParams = { q: query, limit: 10 };
      const response = await searchEntraIDUsers(params);
      
      setState(prev => ({
        ...prev,
        results: response.items,
        isLoading: false,
        hasSearched: true,
        error: response.items.length === 0 ? 'Aucun utilisateur trouvé' : null,
      }));
    } catch (error) {
      console.error('[EntraIDUserSelector] Search error:', error);
      setState(prev => ({
        ...prev,
        results: [],
        isLoading: false,
        hasSearched: true,
        error: 'Erreur lors de la recherche. Réessayez.',
      }));
    }
  }, []);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newQuery = e.target.value;
    setState(prev => ({ ...prev, query: newQuery }));

    // Clear previous timeout
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }

    // Debounce search (wait 500ms after user stops typing)
    const timeout = setTimeout(() => {
      performSearch(newQuery);
    }, 500);

    setSearchTimeout(timeout);
  }, [searchTimeout, performSearch]);

  const handleSelectUser = useCallback((user: EntraIDUser) => {
    onSelectUser(user);
    // Clear search after selection
    setState({
      query: '',
      results: [],
      isLoading: false,
      error: null,
      hasSearched: false,
    });
  }, [onSelectUser]);

  useEffect(() => {
    return () => {
      if (searchTimeout) {
        clearTimeout(searchTimeout);
      }
    };
  }, [searchTimeout]);

  return (
    <div className={`relative ${className}`}>
      {/* Search Input */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground pointer-events-none" />
        <Input
          type="text"
          value={state.query}
          onChange={handleInputChange}
          placeholder={placeholder}
          className="h-11 pl-9 pr-10 rounded-2xl bg-background/95"
        />
        {state.isLoading && (
          <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-blue-600" />
        )}
      </div>

      {/* Search Results */}
      {state.hasSearched && state.results.length > 0 && (
        <div className="absolute z-50 mt-2 w-full rounded-2xl border border-border bg-white shadow-xl">
          <div className="max-h-80 overflow-y-auto p-2">
            {state.results.map((user) => (
              <button
                key={user.id}
                onClick={() => handleSelectUser(user)}
                className="flex w-full items-start gap-3 rounded-xl p-3 text-left transition-colors hover:bg-blue-50"
              >
                <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-blue-100">
                  <User className="h-5 w-5 text-blue-600" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="mb-1 font-semibold text-slate-900 truncate">
                    {user.displayName}
                  </div>
                  <div className="flex flex-col gap-1 text-xs text-slate-600">
                    {user.mail && (
                      <div className="flex items-center gap-1.5 truncate">
                        <Mail className="h-3 w-3 flex-shrink-0" />
                        <span className="truncate">{user.mail}</span>
                      </div>
                    )}
                    {user.jobTitle && (
                      <div className="flex items-center gap-1.5 truncate">
                        <Briefcase className="h-3 w-3 flex-shrink-0" />
                        <span className="truncate">{user.jobTitle}</span>
                      </div>
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Error Message */}
      {state.hasSearched && state.error && (
        <div className="mt-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {state.error}
        </div>
      )}

      {/* Help Text */}
      {!state.hasSearched && state.query.length > 0 && state.query.length < 2 && (
        <div className="mt-2 text-xs text-muted-foreground">
          Saisissez au moins 2 caractères pour rechercher
        </div>
      )}
    </div>
  );
};
