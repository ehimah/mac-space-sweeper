import {promises as fs} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';

export type ScanItem = {
	name: string;
	path: string;
	sizeBytes: number;
	sizeHuman: string;
};

export type Category = {
	key: string;
	label: string;
	description: string;
	recommended: boolean;
	totalBytes: number;
	totalHuman: string;
	items: ScanItem[];
};

export type ScanResult = {
	categories: Category[];
	uniqueTotalBytes: number;
	uniqueTotalHuman: string;
	uniqueTargets: ScanItem[];
};

const currentFile = fileURLToPath(import.meta.url);
const currentDir = path.dirname(currentFile);
const pythonScriptPath = path.resolve(currentDir, '../../scripts/mac_junk_cleaner.py');

export const formatBytes = (size: number): string => {
	const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
	let value = size;
	let unitIndex = 0;

	while (value >= 1024 && unitIndex < units.length - 1) {
		value /= 1024;
		unitIndex += 1;
	}

	if (unitIndex === 0) {
		return `${Math.round(value)} ${units[unitIndex]}`;
	}

	if (value >= 100) {
		return `${value.toFixed(0)} ${units[unitIndex]}`;
	}

	if (value >= 10) {
		return `${value.toFixed(1)} ${units[unitIndex]}`;
	}

	return `${value.toFixed(2)} ${units[unitIndex]}`;
};

export const runScan = async (options: {all?: boolean; categories?: string[]}): Promise<ScanResult> => {
	const args = [pythonScriptPath, 'scan-json'];
	if (options.all) {
		args.push('--all');
	}

	for (const category of options.categories ?? []) {
		args.push('--category', category);
	}

	return new Promise<ScanResult>((resolve, reject) => {
		const child = spawn('python3', args, {
			stdio: ['ignore', 'pipe', 'pipe'],
		});

		let stdout = '';
		let stderr = '';

		child.stdout.on('data', chunk => {
			stdout += String(chunk);
		});

		child.stderr.on('data', chunk => {
			stderr += String(chunk);
		});

		child.on('error', error => {
			reject(error);
		});

		child.on('close', code => {
			if (code !== 0) {
				reject(new Error(stderr.trim() || `Scanner exited with code ${code ?? 'unknown'}`));
				return;
			}

			try {
				resolve(JSON.parse(stdout) as ScanResult);
			} catch (error) {
				reject(error);
			}
		});
	});
};

export const dedupeSelectedTargets = (
	categories: Category[],
	selectedKeys: Set<string>,
): ScanItem[] => {
	const deduped = new Map<string, ScanItem>();
	for (const category of categories) {
		if (!selectedKeys.has(category.key)) {
			continue;
		}

		for (const item of category.items) {
			if (!deduped.has(item.path)) {
				deduped.set(item.path, item);
			}
		}
	}

	return [...deduped.values()].sort((left, right) => right.sizeBytes - left.sizeBytes);
};

export const removePath = async (targetPath: string): Promise<void> => {
	const stats = await fs.lstat(targetPath);
	if (stats.isDirectory() && !stats.isSymbolicLink()) {
		await fs.rm(targetPath, {recursive: true, force: false});
		return;
	}

	await fs.unlink(targetPath);
};
