/**
 * API client for communicating with the backend.
 */

import type { ApiError } from '$types';

const API_BASE = '/api';

/**
 * Thrown by the HTTP wrapper when the backend returns a non-2xx
 * response. Subclasses `Error` so existing `catch (e) { e.message }`
 * sites keep working — `super(detail)` populates `.message`. New code
 * branches on `.status` / `.detail` / `instanceof ApiResponseError` to
 * route errors to the right modal (e.g. HTTP 409 with "is in status"
 * → LifecycleConflictModal).
 */
export class ApiResponseError extends Error {
	constructor(
		public status: number,
		public detail: string,
		public body: unknown
	) {
		super(detail);
		this.name = 'ApiResponseError';
	}
}

export class ApiClient {
	private token: string | null = null;

	setToken(token: string | null) {
		this.token = token;
	}

	private async request<T>(
		endpoint: string,
		options: RequestInit = {}
	): Promise<T> {
		const url = `${API_BASE}${endpoint}`;
		                const headers: Record<string, string> = {
		                        'Content-Type': 'application/json',
		                        ...(options.headers as Record<string, string> || {})
		                };
		
		                if (this.token) {
		                        headers['Authorization'] = `Bearer ${this.token}`;
		                }
		const response = await fetch(url, {
			...options,
			headers
		});

		if (!response.ok) {
			const body: ApiError = await response.json().catch(() => ({
				detail: `HTTP ${response.status}: ${response.statusText}`
			}));
			throw new ApiResponseError(response.status, body.detail, body);
		}

		// Handle empty responses
		const text = await response.text();
		if (!text) {
			return {} as T;
		}

		return JSON.parse(text);
	}

	async get<T>(endpoint: string): Promise<T> {
		return this.request<T>(endpoint, { method: 'GET' });
	}

	async post<T>(endpoint: string, data?: unknown): Promise<T> {
		return this.request<T>(endpoint, {
			method: 'POST',
			body: data ? JSON.stringify(data) : undefined
		});
	}

	async put<T>(endpoint: string, data?: unknown): Promise<T> {
		return this.request<T>(endpoint, {
			method: 'PUT',
			body: data ? JSON.stringify(data) : undefined
		});
	}

	async patch<T>(endpoint: string, data?: unknown): Promise<T> {
		return this.request<T>(endpoint, {
			method: 'PATCH',
			body: data ? JSON.stringify(data) : undefined
		});
	}

	async delete<T>(endpoint: string): Promise<T> {
		return this.request<T>(endpoint, { method: 'DELETE' });
	}
}

export const api = new ApiClient();
