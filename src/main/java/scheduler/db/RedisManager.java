package scheduler.db;

import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPool;
import redis.clients.jedis.JedisPoolConfig;

public class RedisManager {
    private static final JedisPool jedisPool;

    static {
        JedisPoolConfig poolConfig = new JedisPoolConfig();
        poolConfig.setMaxTotal(2000); // Align with Tomcat threads; 5000 concurrent need enough Jedis conns
        poolConfig.setMaxIdle(500);  // Maximum idle connections
        poolConfig.setMinIdle(50);  // Minimum idle connections
        poolConfig.setTestOnBorrow(false); // Skip validation for speed (Redis is local, stable)
        
        // Connect to Redis. Read endpoint from environment variable if available.
        String redisHost = System.getenv("RedisEndpoint");
        if (redisHost == null || redisHost.isEmpty()) {
            redisHost = "localhost";
        }
        jedisPool = new JedisPool(poolConfig, redisHost, 6379);
    }

    /**
     * Get a Jedis connection from the pool.
     * Usage: try (Jedis jedis = RedisManager.getJedis()) { ... }
     */
    public static Jedis getJedis() {
        return jedisPool.getResource();
    }
    
    /**
     * Gracefully close the pool when application shuts down
     */
    public static void closePool() {
        if (jedisPool != null && !jedisPool.isClosed()) {
            jedisPool.close();
        }
    }
}
