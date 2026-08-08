import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict, Any

PAST_POSTMORTEMS: List[Dict[str, Any]] = [
    {
        "id": "INC-041",
        "title": "Auth Service Out of Memory (OOM KILLED)",
        "incident_type": "memory_leak",
        "keywords": "memory leak garbage collection heap allocation oom killed auth service auth-pod cgo memory growth",
        "root_cause": "Unbounded session cache growth in auth-service container under high concurrency, causing node memory pressure and OOM kill.",
        "mitigation": "Restart auth-service pod deployment, trigger garbage collection, and temporarily double memory limits.",
        "blast_radius": "restarts 1 pod, ~10s downtime, affects auth-service only",
        "historical_resolution_time": "3m 12s",
        "confidence_boost": 0.94
    },
    {
        "id": "INC-023",
        "title": "PostgreSQL Primary Connection Pool Exhaustion",
        "incident_type": "high_latency",
        "keywords": "database connection pool active connections high latency thread starvation pgpool timeout read replica",
        "root_cause": "Long-running unindexed query held open transaction locks, exhausting backend connection pool max limit of 200.",
        "mitigation": "Terminate idle transactions, scale connection pool limit to 400, and flush query cache.",
        "blast_radius": "no pod restart, zero downtime, affects read-write db connections",
        "historical_resolution_time": "1m 45s",
        "confidence_boost": 0.91
    },
    {
        "id": "INC-012",
        "title": "Node Storage Volume Log Rotation Failure",
        "incident_type": "disk_full",
        "keywords": "disk full root partition 98% capacity log rotation access.log var log containers inode exhaustion",
        "root_cause": "Systemd logrotate daemon stalled on compressed archive lock, allowing container access.log to consume 98% of /var/log.",
        "mitigation": "Truncate uncompressed raw logs, force logrotate execution, and enable auto-pruning.",
        "blast_radius": "no pod restart, zero downtime, affects host log storage only",
        "historical_resolution_time": "45s",
        "confidence_boost": 0.98
    },
    {
        "id": "INC-055",
        "title": "Redis Cache Cluster Memory Spike",
        "incident_type": "memory_leak",
        "keywords": "redis cache evicted keys memory limit maxmemory volatile-lru memory growth session store",
        "root_cause": "TTL expiration omitted on user session tokens created during flash promo campaign.",
        "mitigation": "Apply default TTL policy of 86400s across all session keys and execute UNLINK on stale keys.",
        "blast_radius": "no pod restart, zero downtime, affects non-persistent session cache",
        "historical_resolution_time": "2m 10s",
        "confidence_boost": 0.89
    },
    {
        "id": "INC-089",
        "title": "Ingress Nginx Controller Rate Limit Burst",
        "incident_type": "high_latency",
        "keywords": "nginx ingress 502 bad gateway rate limit HTTP 429 packet queue latency spike upstream timeout",
        "root_cause": "DDoS protection ingress rule triggered false positive due to client IP spoofing in load balancer headers.",
        "mitigation": "Update ingress rate-limit annotation from 100r/s to 500r/s per client IP and reload ingress controller.",
        "blast_radius": "reloads ingress config, zero downtime, affects global API ingress",
        "historical_resolution_time": "1m 15s",
        "confidence_boost": 0.93
    },
    {
        "id": "INC-104",
        "title": "API Gateway Thread Pool Saturation",
        "incident_type": "high_latency",
        "keywords": "api gateway latency spike 504 gateway timeout downstream service bottleneck worker thread pool",
        "root_cause": "Synchronous RPC call to legacy payment gateway stalled execution threads under high load.",
        "mitigation": "Enable circuit breaker fallback for payment API and auto-scale API gateway replicas from 3 to 6.",
        "blast_radius": "scales 3 additional pods, zero downtime, affects API gateway traffic",
        "historical_resolution_time": "1m 30s",
        "confidence_boost": 0.95
    },
    {
        "id": "INC-118",
        "title": "Async Worker Queue Event Accumulation",
        "incident_type": "memory_leak",
        "keywords": "celery rabbitmq queue memory growth unconsumed messages backpressure dead letter queue event leak",
        "root_cause": "Malformed event payload caused worker process to endlessly retry without acking.",
        "mitigation": "Move poisoned messages to Dead Letter Queue (DLQ) and purge temporary worker memory buffer.",
        "blast_radius": "restarts worker pool, ~5s downtime, affects async task processing",
        "historical_resolution_time": "2m 40s",
        "confidence_boost": 0.87
    },
    {
        "id": "INC-132",
        "title": "Kubernetes Ephemeral Storage Exceeded",
        "incident_type": "disk_full",
        "keywords": "ephemeral storage request exceeded pod evicted crashloopbackoff tmp directory fill up node disk pressure",
        "root_cause": "Data processing pod wrote uncompressed temporary CSV files to local container storage layer.",
        "mitigation": "Clear /tmp artifacts, attach dedicated PVC storage volume, and purge temporary data buffer.",
        "blast_radius": "clears container /tmp, zero downtime, affects local node ephemeral disk",
        "historical_resolution_time": "50s",
        "confidence_boost": 0.96
    }
]

class VectorStore:
    def __init__(self, postmortems: List[Dict[str, Any]] = PAST_POSTMORTEMS):
        self.postmortems = postmortems
        self.vectorizer = TfidfVectorizer(stop_words='english')
        
        # Prepare corpus text combining title, incident_type, keywords, root_cause, mitigation
        self.corpus = [
            f"{p['title']} {p['incident_type']} {p['keywords']} {p['root_cause']} {p['mitigation']}"
            for p in self.postmortems
        ]
        self.doc_vectors = self.vectorizer.fit_transform(self.corpus)

    def search_similar_incidents(self, query_text: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """
        Embed query_text and perform cosine similarity search against seeded postmortems.
        Returns top_k matching postmortem records with similarity scores.
        """
        if not query_text or not query_text.strip():
            return self.postmortems[:top_k]
            
        query_vec = self.vectorizer.transform([query_text])
        similarities = cosine_similarity(query_vec, self.doc_vectors).flatten()
        
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            pm = self.postmortems[idx].copy()
            pm["similarity_score"] = float(round(similarities[idx], 3))
            results.append(pm)
            
        return results

# Global singleton vector store instance
vector_store = VectorStore()
