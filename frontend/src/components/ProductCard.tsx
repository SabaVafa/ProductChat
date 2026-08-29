import { ProductCard as ProductCardType } from '../types';
import { ExternalLink } from 'lucide-react';
import { safeUrl, formatPrice } from '../utils/format';

interface ProductCardProps {
  product: ProductCardType;
}

export default function ProductCard({ product }: ProductCardProps) {
  // XSS guard: only http(s) URLs are ever rendered (audit finding H3).
  const url = safeUrl(product.url);
  const image = safeUrl(product.image);

  const CardMedia = image && (
    <div className="relative h-48 bg-gray-100">
      <img
        src={image}
        alt={product.name}
        className="w-full h-full object-cover"
        onError={(e) => {
          e.currentTarget.style.display = 'none';
        }}
      />
      {product.popular && (
        <span className="absolute top-2 left-2 text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200 rounded-full px-2 py-0.5">
          Beliebt
        </span>
      )}
    </div>
  );

  return (
    <div className="bg-white rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow flex flex-col">
      {url ? (
        <a href={url} target="_blank" rel="noopener noreferrer">
          {CardMedia}
        </a>
      ) : (
        CardMedia
      )}
      <div className="p-4 flex flex-col flex-1">
        <h3 className="font-semibold text-lg text-gray-900 mb-2">{product.name}</h3>
        {product.price !== undefined && product.price !== null && (
          <p className="text-2xl font-bold text-green-600 mb-2">
            {product.has_variants ? 'ab ' : ''}
            {formatPrice(product.price)}
          </p>
        )}
        {product.reason && (
          <p className="text-sm text-gray-600 mb-3">{product.reason}</p>
        )}
        {product.score !== undefined && (
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs text-gray-500">Relevance:</span>
            <div className="flex-1 bg-gray-200 rounded-full h-2">
              <div
                className="bg-blue-600 h-2 rounded-full"
                style={{ width: `${(product.score * 100).toFixed(0)}%` }}
              />
            </div>
            <span className="text-xs text-gray-500">{(product.score * 100).toFixed(0)}%</span>
          </div>
        )}
        <div className="mt-auto pt-2">
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              View product
            </a>
          ) : (
            <button
              disabled
              className="w-full flex items-center justify-center gap-2 border border-gray-300 text-gray-400 px-4 py-2 rounded-lg cursor-not-allowed"
            >
              <ExternalLink className="w-4 h-4" />
              No link available
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
