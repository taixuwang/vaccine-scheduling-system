package scheduler.db;

import redis.clients.jedis.Jedis;

public class RedisTest {
    public static void main(String[] args) {
        System.out.println("Attempting to connect to Redis (localhost:6379)...");
        
        try (Jedis jedis = RedisManager.getJedis()) {
            // ping() sends a PING command to the Redis server
            // If the connection is successful, the server responds with "PONG"
            String response = jedis.ping();
            
            System.out.println("=========================================");
            System.out.println("🎉 Connection successful!");
            System.out.println("✅ Server responded with: " + response);
            System.out.println("=========================================");
            
        } catch (Exception e) {
            System.out.println("=========================================");
            System.out.println("❌ Failed to connect to Redis!");
            System.out.println("Please make sure your Redis server is running on localhost:6379");
            System.out.println("Error details:");
            System.out.println("=========================================");
            e.printStackTrace();
        } finally {
            // Close the pool so the program can exit gracefully
            RedisManager.closePool();
        }
    }
}
